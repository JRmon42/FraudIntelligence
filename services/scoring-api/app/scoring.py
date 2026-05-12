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


class OnnxScorer:
    """Scoring engine. Loads ONNX model if present; otherwise uses a stub."""

    def __init__(self, model_path: str, model_version: str) -> None:
        self._model_path = model_path
        self._version = model_version
        self._session: Any | None = None
        self._input_name: str | None = None
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
            self._input_name = self._session.get_inputs()[0].name
            log.info("onnx_model_loaded", path=self._model_path, version=self._version)
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
        vec = build_feature_vector(ctx)
        if self._session is None or self._input_name is None:
            return _stub_score(ctx, vec)
        try:
            out = self._session.run(None, {self._input_name: vec})
            raw = out[0]
            arr = np.asarray(raw).reshape(-1)
            return float(np.clip(arr[0], 0.0, 1.0))
        except Exception as exc:  # noqa: BLE001
            log.error("onnx_inference_failed", err=str(exc))
            return _stub_score(ctx, vec)


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
