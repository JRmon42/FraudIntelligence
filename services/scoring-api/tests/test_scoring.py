"""Unit tests for ONNX scorer fallback + feature vector."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import Aggregates, CardFeatures, MerchantFeatures, ScoreRequest
from app.scoring import FEATURE_NAMES, OnnxScorer, ScoringContext, build_feature_vector


def _ctx(amount: float = 50.0, blocked: bool = False) -> ScoringContext:
    req = ScoreRequest(
        transaction_id="t1",
        card_id="c1",
        merchant_id="m1",
        amount=amount,
        currency="EUR",
        country="SE",
        channel="ECOM",
        timestamp=datetime(2025, 5, 12, 10, 0, tzinfo=UTC),
        device_fingerprint="fp",
        ip="1.1.1.1",
    )
    card = CardFeatures(card_id="c1", risk_tier=2, issue_country="SE", is_blocked=blocked)
    merch = MerchantFeatures(merchant_id="m1", risk_score=0.1, country="SE")
    return ScoringContext(request=req, card=card, merchant=merch, aggregates=Aggregates())


def test_feature_vector_shape_matches_names() -> None:
    vec = build_feature_vector(_ctx())
    assert vec.shape == (1, len(FEATURE_NAMES))


def test_onnx_missing_falls_back_to_stub_without_crash() -> None:
    scorer = OnnxScorer("/does/not/exist.onnx", "v0.0.0")
    assert scorer.loaded is False
    s = scorer.score(_ctx())
    assert 0.0 <= s <= 1.0
    assert scorer.model_version.endswith("+stub")


def test_stub_score_high_for_blocked_card() -> None:
    scorer = OnnxScorer("/does/not/exist.onnx", "v0.0.0")
    s = scorer.score(_ctx(blocked=True))
    assert s >= 0.85


def test_stub_score_deterministic_for_same_inputs() -> None:
    scorer = OnnxScorer("/does/not/exist.onnx", "v0.0.0")
    a = scorer.score(_ctx())
    b = scorer.score(_ctx())
    assert a == b
