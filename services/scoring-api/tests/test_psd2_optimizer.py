"""Unit tests for the PSD2 exemption optimiser."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models import CardFeatures, MerchantFeatures, ScoreRequest
from app.psd2_optimizer import (
    ExemptionContext,
    decide,
    is_low_value_eligible,
    is_tra_eligible,
    select_exemption,
)


def _req(amount: float = 25.0, country: str = "SE", channel: str = "ECOM") -> ScoreRequest:
    return ScoreRequest(
        transaction_id="t1",
        card_id="c1",
        merchant_id="m1",
        amount=amount,
        currency="EUR",
        country=country,
        channel=channel,  # type: ignore[arg-type]
        timestamp=datetime(2025, 5, 12, 10, 0, tzinfo=UTC),
        device_fingerprint="fp",
        ip="1.1.1.1",
    )


def test_low_value_eligible_under_threshold() -> None:
    ctx = ExemptionContext(request=_req(amount=20), card=None, merchant=None, score=0.1)
    assert is_low_value_eligible(ctx) is True


def test_low_value_blocked_when_over_threshold() -> None:
    ctx = ExemptionContext(request=_req(amount=35), card=None, merchant=None, score=0.1)
    assert is_low_value_eligible(ctx) is False


def test_low_value_blocked_when_cumulative_exceeded() -> None:
    ctx = ExemptionContext(
        request=_req(amount=20),
        card=None,
        merchant=None,
        cumulative_amount_eur=95.0,
        score=0.1,
    )
    assert is_low_value_eligible(ctx) is False


def test_low_value_blocked_for_non_eea_country() -> None:
    ctx = ExemptionContext(request=_req(amount=10, country="US"), card=None, merchant=None)
    assert is_low_value_eligible(ctx) is False


def test_tra_eligible_low_amount_low_fraud() -> None:
    merch = MerchantFeatures(merchant_id="m1", country="SE", fraud_rate_30d=0.0005)
    ctx = ExemptionContext(request=_req(amount=80), card=None, merchant=merch, score=0.1)
    assert is_tra_eligible(ctx) is True


def test_tra_blocked_high_fraud_rate() -> None:
    merch = MerchantFeatures(merchant_id="m1", country="SE", fraud_rate_30d=0.02)
    ctx = ExemptionContext(request=_req(amount=80), card=None, merchant=merch)
    assert is_tra_eligible(ctx) is False


def test_select_exemption_prefers_corporate() -> None:
    card = CardFeatures(card_id="c1", customer_segment="corporate")
    merch = MerchantFeatures(merchant_id="m1", country="SE", fraud_rate_30d=0.00001)
    ctx = ExemptionContext(request=_req(amount=20), card=card, merchant=merch, score=0.1)
    assert select_exemption(ctx) == "CORPORATE"


def test_select_exemption_returns_none_for_high_score() -> None:
    merch = MerchantFeatures(merchant_id="m1", country="SE", fraud_rate_30d=0.00001)
    ctx = ExemptionContext(request=_req(amount=20), card=None, merchant=merch, score=0.92)
    assert select_exemption(ctx) == "NONE"


def test_select_exemption_picks_tra_over_low_value_when_both_apply() -> None:
    merch = MerchantFeatures(merchant_id="m1", country="SE", fraud_rate_30d=0.00005)
    # amount=25 → both LOW_VALUE & TRA apply; TRA preferred.
    ctx = ExemptionContext(request=_req(amount=25), card=None, merchant=merch, score=0.1)
    assert select_exemption(ctx) == "TRA"


def test_decide_blocked_card_always_declined() -> None:
    card = CardFeatures(card_id="c1", is_blocked=True)
    assert decide(0.01, "TRA", card) == "DECLINE"


def test_decide_high_score_declined() -> None:
    assert decide(0.9, "NONE", None) == "DECLINE"


def test_decide_medium_score_no_exemption_triggers_sca() -> None:
    assert decide(0.5, "NONE", None) == "SCA"


def test_decide_medium_score_with_exemption_approves() -> None:
    assert decide(0.4, "TRA", None) == "APPROVE"


@pytest.mark.parametrize("amount,expected", [(10, True), (50, False)])
def test_low_value_threshold_parametrised(amount: float, expected: bool) -> None:
    ctx = ExemptionContext(request=_req(amount=amount), card=None, merchant=None)
    assert is_low_value_eligible(ctx) is expected
