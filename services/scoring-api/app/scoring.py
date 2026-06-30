"""ONNX Runtime ensemble scorer with deterministic stub fallback."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog

from .models import Aggregates, CardFeatures, MerchantFeatures, ScoreRequest

log = structlog.get_logger(__name__)


# Static feature vector layout (kept stable for model contract).
FEATURE_NAMES: tuple[str, ...] = (
    "amount",
    "amount_log1p",
    "is_ecom",
    "is_pos",
    "card_risk_tier",
    "card_chargebacks_30d",
    "card_blocked",
    "merchant_risk_score",
    "merchant_high_risk",
    "merchant_fraud_rate_30d",
    "agg_amount_1h",
    "agg_count_1h",
    "agg_declined_1h",
    "country_match",
)


@dataclass
class ScoringContext:
    """Bundle passed to the model for both the ONNX and stub paths."""

    request: ScoreRequest
    card: CardFeatures | None
    merchant: MerchantFeatures | None
    aggregates: Aggregates


def build_feature_vector(ctx: ScoringContext) -> np.ndarray:
    """Materialise the float32 vector consumed by the model."""

    req = ctx.request
    card = ctx.card
    merch = ctx.merchant
    agg = ctx.aggregates
    country_match = (
        1.0 if (card and card.issue_country and card.issue_country == req.country) else 0.0
    )

    vec = np.array(
        [
            float(req.amount),
            float(np.log1p(max(req.amount, 0.0))),
            1.0 if req.channel == "ECOM" else 0.0,
            1.0 if req.channel == "POS" else 0.0,
            float(card.risk_tier) if card else 0.0,
            float(card.chargebacks_30d) if card else 0.0,
            1.0 if card and card.is_blocked else 0.0,
            float(merch.risk_score) if merch else 0.0,
            1.0 if merch and merch.high_risk else 0.0,
            float(merch.fraud_rate_30d) if merch else 0.0,
            float(agg.amount_1h),
            float(agg.count_1h),
            float(agg.declined_1h),
            country_match,
        ],
        dtype=np.float32,
    )
    return vec.reshape(1, -1)


# Named inputs expected by the trained stacked-ensemble ONNX graph
# (XGBoost + LightGBM + Logistic, exported from ml/train_ensemble.py). The model
# consumes behavioural / contextual features; hard business rules such as a
# blocked card are applied by the policy layer (psd2_optimizer), not the model.
GNN_EMB_DIM = 16
ONNX_NUM_INPUTS: tuple[str, ...] = (
    "amount", "amount_log", "hour", "dow", "is_weekend",
    "card_age_days", "merchant_risk", "card_txn_count_24h",
    "card_amount_sum_24h", "card_distinct_merchants_24h",
    # GNN-derived per-card features (published into the feature store by the
    # nightly fraud-ring GraphSAGE job). These wire the GNN into the live
    # decision: a known ring card scores high regardless of amount / time.
    "card_ring_score",
    *(f"card_emb_{i}" for i in range(GNN_EMB_DIM)),
)
ONNX_CAT_INPUTS: tuple[str, ...] = (
    "card_country", "merchant_country", "ip_country",
    "card_brand", "channel", "device_os", "mcc",
)


def build_onnx_inputs(ctx: ScoringContext) -> dict[str, np.ndarray]:
    """Materialise the per-column named tensors consumed by the ensemble ONNX.

    Each input is shaped ``[1, 1]``; numeric columns are float32, categorical
    columns are object (string) arrays. Fields absent from the online request /
    feature schema are derived or defaulted; the model's OneHotEncoder was fit
    with ``handle_unknown="ignore"`` so unseen categories degrade gracefully.
    """

    req = ctx.request
    card = ctx.card
    merch = ctx.merchant
    agg = ctx.aggregates

    amount = float(req.amount)
    dow = float(req.timestamp.weekday())
    num = {
        "amount": amount,
        "amount_log": float(np.log1p(max(amount, 0.0))),
        "hour": float(req.timestamp.hour),
        "dow": dow,
        "is_weekend": 1.0 if dow >= 5 else 0.0,
        "card_age_days": float(card.card_age_days) if card else 800.0,
        "merchant_risk": float(merch.risk_score) if merch else 0.0,
        "card_txn_count_24h": float(agg.count_1h),
        "card_amount_sum_24h": float(agg.amount_1h),
        # Not tracked online; default to a benign baseline.
        "card_distinct_merchants_24h": 1.0,
        # GNN signal from the feature store (0 / zero-vector for cards without a
        # published embedding -> the model falls back to behavioural features).
        "card_ring_score": float(card.ring_score) if card else 0.0,
    }
    emb = (card.gnn_embedding if card and card.gnn_embedding else [0.0] * GNN_EMB_DIM)
    for i in range(GNN_EMB_DIM):
        num[f"card_emb_{i}"] = float(emb[i]) if i < len(emb) else 0.0
    cat = {
        "card_country": (card.issue_country if card and card.issue_country else req.country),
        "merchant_country": (merch.country if merch and merch.country else req.country),
        # We do not geo-resolve the source IP online; use the txn country as proxy.
        "ip_country": req.country,
        "card_brand": (card.card_brand if card else "VISA"),
        "channel": req.channel.lower(),
        "device_os": "unknown",
        "mcc": (str(merch.mcc) if merch else "0000"),
    }

    feed: dict[str, np.ndarray] = {}
    for name in ONNX_NUM_INPUTS:
        feed[name] = np.array([[num[name]]], dtype=np.float32)
    for name in ONNX_CAT_INPUTS:
        feed[name] = np.array([[cat[name]]], dtype=object)
    return feed


class OnnxScorer:
    """Scoring engine. Loads ONNX model if present; otherwise uses a stub."""

    def __init__(self, model_path: str, model_version: str) -> None:
        self._model_path = model_path
        self._version = model_version
        self._session: Any | None = None
        self._input_names: list[str] = []
        self._output_names: list[str] = []
        self._vector_input: str | None = None
        self._loaded = self._load()

    def _load(self) -> bool:
        if not os.path.exists(self._model_path):
            log.warning(
                "onnx_model_missing",
                path=self._model_path,
                action="falling back to deterministic stub scorer",
            )
            return False
        try:
            import onnxruntime as ort

            so = ort.SessionOptions()
            so.intra_op_num_threads = 1
            so.inter_op_num_threads = 1
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                self._model_path, sess_options=so, providers=["CPUExecutionProvider"]
            )
            inputs = self._session.get_inputs()
            self._input_names = [i.name for i in inputs]
            self._output_names = [o.name for o in self._session.get_outputs()]
            # A single tensor input means a legacy flat-vector model; multiple
            # named inputs means the stacked-ensemble per-column contract.
            self._vector_input = inputs[0].name if len(inputs) == 1 else None
            log.info(
                "onnx_model_loaded",
                path=self._model_path,
                version=self._version,
                inputs=len(self._input_names),
                outputs=self._output_names,
            )
            return True
        except Exception as exc:  # noqa: BLE001 - never crash the hot path
            log.error("onnx_model_load_failed", path=self._model_path, err=str(exc))
            self._session = None
            return False

    @property
    def model_version(self) -> str:
        return self._version if self._loaded else f"{self._version}+stub"

    @property
    def loaded(self) -> bool:
        return self._loaded

    def score(self, ctx: ScoringContext) -> float:
        if self._session is None:
            return _stub_score(ctx, build_feature_vector(ctx))
        try:
            if self._vector_input is not None:
                feed: dict[str, np.ndarray] = {self._vector_input: build_feature_vector(ctx)}
            else:
                feed = build_onnx_inputs(ctx)
            outs = self._session.run(self._output_names, feed)
            result = dict(zip(self._output_names, outs))
            return _extract_fraud_probability(result, outs)
        except Exception as exc:  # noqa: BLE001
            log.error("onnx_inference_failed", err=str(exc))
            return _stub_score(ctx, build_feature_vector(ctx))


def _extract_fraud_probability(result: dict[str, Any], outs: list[Any]) -> float:
    """Pull the positive-class fraud probability from the model outputs.

    Handles the skl2onnx classifier contract (``label`` + ``probabilities``
    [N, 2]) as well as a plain single-probability regression output.
    """

    proba = result.get("probabilities")
    if proba is not None:
        arr = np.asarray(proba)
        if arr.ndim == 2 and arr.shape[1] >= 2:
            return float(np.clip(arr[0, 1], 0.0, 1.0))
        return float(np.clip(arr.reshape(-1)[-1], 0.0, 1.0))
    arr = np.asarray(outs[-1]).reshape(-1)
    return float(np.clip(arr[-1], 0.0, 1.0))


def _stub_score(ctx: ScoringContext, vec: np.ndarray) -> float:
    """Deterministic, bounded stub. Combines explicit risk signals with a hash jitter."""

    req = ctx.request
    card = ctx.card
    merch = ctx.merchant
    agg = ctx.aggregates

    base = 0.05
    if card and card.is_blocked:
        base += 0.85
    if merch and merch.high_risk:
        base += 0.30
    if merch:
        base += min(merch.fraud_rate_30d, 0.5)
    if card:
        base += min(card.risk_tier * 0.05, 0.25)
        base += min(card.chargebacks_30d * 0.05, 0.25)
    if req.amount > 1000:
        base += 0.15
    if agg.declined_1h > 2:
        base += 0.20
    if agg.count_1h > 20:
        base += 0.10

    digest = hashlib.blake2b(
        f"{req.transaction_id}|{req.card_id}|{req.merchant_id}".encode(), digest_size=4
    ).digest()
    jitter = int.from_bytes(digest, "big") / 0xFFFFFFFF * 0.05
    return float(min(max(base + jitter, 0.0), 1.0))
