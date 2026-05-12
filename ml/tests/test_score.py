"""Tests for the online scoring entrypoint."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

import ml.score as score


REQUIRED_ARTIFACTS = [
    Path(__file__).resolve().parents[1] / "artifacts" / "ensemble.onnx",
]


def _has_artifacts() -> bool:
    return all(p.exists() for p in REQUIRED_ARTIFACTS)


@pytest.fixture(scope="module", autouse=True)
def _setup_module():
    if not _has_artifacts():
        pytest.skip("ensemble.onnx not present — run ml.train_ensemble first")
    score._SESSION = None
    score._EMB_MAP = {}
    score.init()


def _sample(n: int = 1):
    base = {
        "card_id": "c_000001",
        "amount": 142.5, "amount_log": float(np.log1p(142.5)),
        "hour": 14, "dow": 2, "is_weekend": 0,
        "card_age_days": 720, "merchant_risk": 0.05,
        "card_txn_count_24h": 3, "card_amount_sum_24h": 450.0,
        "card_distinct_merchants_24h": 2,
        "card_country": "SE", "merchant_country": "SE", "ip_country": "SE",
        "card_brand": "VISA", "channel": "ecom", "device_os": "iOS",
        "mcc": "5411",
    }
    return [base.copy() for _ in range(n)]


def test_run_returns_expected_schema():
    out = score.run(_sample(1))
    assert isinstance(out, list) and len(out) == 1
    rec = out[0]
    assert {"fraud_score", "ring_score", "risk_band", "model_version", "scoring_ms"} <= rec.keys()
    assert 0.0 <= rec["fraud_score"] <= 1.0
    assert rec["risk_band"] in {"approve", "monitor", "step_up", "decline"}


def test_run_accepts_json_string():
    payload = json.dumps({"data": _sample(3)})
    out = score.run(payload)
    assert len(out) == 3


def test_inference_is_under_5ms():
    # Warm-up
    for _ in range(20):
        score.run(_sample(1))
    times = []
    for _ in range(100):
        t0 = time.perf_counter()
        score.run(_sample(1))
        times.append((time.perf_counter() - t0) * 1000.0)
    p95 = float(np.percentile(times, 95))
    print(f"Single-call p50={np.percentile(times, 50):.3f}ms  p95={p95:.3f}ms")
    assert p95 < 5.0, f"p95 single-call latency {p95:.3f}ms exceeds 5 ms target"
