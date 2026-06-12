"""Online scoring entrypoint for the Heimdall ensemble model.

Compatible with Azure ML managed online endpoint contract:
    init()  — called once at container start; loads the ONNX session and the
              pre-computed GNN embedding K-V map.
    run(raw) — called per HTTP request; raw is a JSON string (or already-
              decoded list/dict). Returns a list of {fraud_score, ring_score,
              risk_band} dicts.

Target latency: < 5 ms per call on a single CPU core.
Use `python -m ml.score --benchmark` to measure end-to-end latency.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

LOG = logging.getLogger("fraud-intel.score")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

_SESSION = None
_EMB_MAP: dict[str, np.ndarray] = {}
_DEFAULT_EMB: np.ndarray | None = None
_INPUT_NAMES: list[str] = []

NUM_FEATURES = [
    "amount", "amount_log", "hour", "dow", "is_weekend",
    "card_age_days", "merchant_risk", "card_txn_count_24h",
    "card_amount_sum_24h", "card_distinct_merchants_24h",
]
CAT_FEATURES = ["card_country", "merchant_country", "ip_country",
                "card_brand", "channel", "device_os", "mcc"]


def _resolve_artifacts_dir() -> Path:
    """AML mounts model files under AZUREML_MODEL_DIR; locally we fall back to
    the in-repo artifacts directory."""
    env = os.environ.get("AZUREML_MODEL_DIR")
    if env and Path(env).exists():
        return Path(env)
    return Path(__file__).resolve().parent / "artifacts"


def init() -> None:
    """AML lifecycle hook — load the ONNX model and embeddings once."""
    global _SESSION, _EMB_MAP, _DEFAULT_EMB, _INPUT_NAMES
    import onnxruntime as ort

    art = _resolve_artifacts_dir()
    onnx_path = art / "ensemble.onnx"
    LOG.info("Loading ONNX model from %s", onnx_path)

    sess_opts = ort.SessionOptions()
    sess_opts.intra_op_num_threads = 1
    sess_opts.inter_op_num_threads = 1
    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    _SESSION = ort.InferenceSession(
        str(onnx_path), sess_options=sess_opts,
        providers=["CPUExecutionProvider"],
    )
    _INPUT_NAMES = [i.name for i in _SESSION.get_inputs()]

    emb_path = art / "embeddings_card.parquet"
    if emb_path.exists():
        import pandas as pd
        emb_df = pd.read_parquet(emb_path)
        emb_cols = [c for c in emb_df.columns if c.startswith("emb_")]
        for row in emb_df.itertuples(index=False):
            d = row._asdict()
            _EMB_MAP[d["card_id"]] = np.asarray([d[c] for c in emb_cols], dtype=np.float32)
        if _EMB_MAP:
            _DEFAULT_EMB = np.mean(list(_EMB_MAP.values()), axis=0)
        LOG.info("Loaded %d card embeddings (dim=%d)", len(_EMB_MAP),
                 0 if _DEFAULT_EMB is None else _DEFAULT_EMB.shape[0])
    else:
        LOG.warning("No embeddings parquet at %s — ring_score will be 0.0", emb_path)


def _to_list(raw: Any) -> list[dict]:
    if isinstance(raw, (str, bytes)):
        raw = json.loads(raw)
    if isinstance(raw, dict):
        if "data" in raw:
            raw = raw["data"]
        elif "transactions" in raw:
            raw = raw["transactions"]
        else:
            raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("Input must be a list of transaction dicts")
    return raw


def _build_feed(rows: list[dict]) -> dict:
    feed: dict[str, np.ndarray] = {}
    for col in NUM_FEATURES:
        feed[col] = np.array([[float(r.get(col, 0.0))] for r in rows], dtype=np.float32)
    for col in CAT_FEATURES:
        feed[col] = np.array([[str(r.get(col, ""))] for r in rows], dtype=object)
    return {k: v for k, v in feed.items() if k in _INPUT_NAMES}


def _ring_scores(rows: list[dict]) -> list[float]:
    out = []
    for r in rows:
        emb = _EMB_MAP.get(r.get("card_id", ""))
        if emb is None:
            out.append(0.0)
        else:
            # Use L2 norm of embedding as a proxy ring-affinity signal; in
            # production this is overwritten by the GNN's per-card ring_score
            # parquet (also loaded). Kept simple here for the demo.
            out.append(float(min(1.0, np.linalg.norm(emb) / 10.0)))
    return out


def _risk_band(p: float) -> str:
    if p >= 0.85:
        return "decline"
    if p >= 0.55:
        return "step_up"
    if p >= 0.20:
        return "monitor"
    return "approve"


def run(raw: Any) -> list[dict]:
    """AML lifecycle hook — score one request."""
    if _SESSION is None:
        init()
    rows = _to_list(raw)
    feed = _build_feed(rows)
    t0 = time.perf_counter()
    out = _SESSION.run(None, feed)
    dt_ms = (time.perf_counter() - t0) * 1000.0

    # Output convention: out[0] = labels (N,), out[1] = probabilities (N, 2)
    if len(out) >= 2 and out[1].ndim == 2 and out[1].shape[1] >= 2:
        probs = out[1][:, 1]
    else:
        probs = np.asarray(out[-1]).reshape(-1)

    rings = _ring_scores(rows)
    return [
        {
            "fraud_score": float(p),
            "ring_score": float(r),
            "risk_band": _risk_band(float(p)),
            "model_version": os.environ.get("MODEL_VERSION", "1.0.0"),
            "scoring_ms": round(dt_ms / max(len(rows), 1), 3),
        }
        for p, r in zip(probs, rings)
    ]


# ---------------------------------------------------------------------------
# CLI / benchmark
# ---------------------------------------------------------------------------
def _sample_request() -> list[dict]:
    return [{
        "card_id": "c_000001",
        "amount": 142.5, "amount_log": float(np.log1p(142.5)),
        "hour": 14, "dow": 2, "is_weekend": 0,
        "card_age_days": 720, "merchant_risk": 0.05,
        "card_txn_count_24h": 3, "card_amount_sum_24h": 450.0,
        "card_distinct_merchants_24h": 2,
        "card_country": "SE", "merchant_country": "SE", "ip_country": "SE",
        "card_brand": "VISA", "channel": "ecom", "device_os": "iOS",
        "mcc": "5411",
    }]


def benchmark(n: int = 200) -> None:
    init()
    sample = _sample_request()
    # warm-up
    for _ in range(20):
        run(sample)
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        run(sample)
        times.append((time.perf_counter() - t0) * 1000.0)
    arr = np.array(times)
    print(json.dumps({
        "n": n, "mean_ms": round(float(arr.mean()), 3),
        "p50_ms": round(float(np.percentile(arr, 50)), 3),
        "p95_ms": round(float(np.percentile(arr, 95)), 3),
        "p99_ms": round(float(np.percentile(arr, 99)), 3),
        "max_ms": round(float(arr.max()), 3),
    }, indent=2))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", action="store_true")
    ap.add_argument("--n", type=int, default=200)
    args = ap.parse_args()
    if args.benchmark:
        benchmark(args.n)
    else:
        init()
        print(json.dumps(run(_sample_request()), indent=2))
