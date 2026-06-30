"""Deterministic demo feature seed for the in-memory feature store.

When ``COSMOS_ENDPOINT`` is unset (local dev and the demo deployment) the
service falls back to :class:`InMemoryFeatureClient`. Without any data every
card/merchant lookup returns ``None``, so the deterministic stub scorer keeps
every transaction at a near-zero risk score and the only possible decision is
APPROVE.

This module ships a small, curated set of *risky* and *clean* entities so the
demo produces a realistic APPROVE / SCA / DECLINE mix that exercises the PSD2
optimiser. It is enabled by ``SEED_DEMO_FEATURES=true`` (see
``Settings.seed_demo_features``).

The entity IDs below are the single source of truth for the demo client
(``scripts/demo_client.py``) and the demo web console (``scripts/demo_web.py``);
keep those in sync when changing IDs.
"""

from __future__ import annotations

from .models import CardFeatures, MerchantFeatures

# --------------------------------------------------------------------------- #
# Canonical demo entity IDs (mirrored by scripts/demo_client.py)
# --------------------------------------------------------------------------- #
DEMO_BLOCKED_CARD = "card-blocked-001"   # is_blocked -> hard DECLINE
DEMO_HOT_CARD = "card-hot-014"           # high risk tier + chargebacks -> SCA
DEMO_CORP_CARD = "card-corp-700"         # corporate -> CORPORATE exemption (APPROVE)
DEMO_FRAUD_MERCHANT = "merch-darkbazaar-66"  # high-risk + high fraud rate -> DECLINE
DEMO_RISKY_MERCHANT = "merch-luckyspin-21"   # high-risk, medium fraud rate -> SCA
DEMO_CLEAN_MERCHANT = "merch-nordstore-5"    # low fraud rate -> TRA exemption (APPROVE)


def demo_cards() -> dict[str, CardFeatures]:
    """Curated card feature records keyed by ``card_id``."""

    return {
        # Blocked card: decide() short-circuits to DECLINE regardless of amount.
        DEMO_BLOCKED_CARD: CardFeatures(
            card_id=DEMO_BLOCKED_CARD,
            risk_tier=5,
            avg_ticket=240.0,
            issue_country="SE",
            chargebacks_30d=4,
            is_blocked=True,
            customer_segment="retail",
        ),
        # "Hot" card: risk_tier 5 (+0.25) + chargebacks (+0.25) pushes the stub
        # score to ~0.55-0.70 -> exemption NONE -> SCA.
        DEMO_HOT_CARD: CardFeatures(
            card_id=DEMO_HOT_CARD,
            risk_tier=5,
            avg_ticket=90.0,
            issue_country="DK",
            chargebacks_30d=6,
            is_blocked=False,
            customer_segment="retail",
        ),
        # Corporate card: low risk -> CORPORATE exemption -> APPROVE (frictionless).
        DEMO_CORP_CARD: CardFeatures(
            card_id=DEMO_CORP_CARD,
            risk_tier=0,
            avg_ticket=1800.0,
            issue_country="SE",
            chargebacks_30d=0,
            is_blocked=False,
            customer_segment="corporate",
        ),
    }


def demo_merchants() -> dict[str, MerchantFeatures]:
    """Curated merchant feature records keyed by ``merchant_id``."""

    return {
        # Fraud merchant: high_risk (+0.30) + fraud_rate 0.55 (+0.50) -> score ~1.0
        # -> DECLINE even with a clean card.
        DEMO_FRAUD_MERCHANT: MerchantFeatures(
            merchant_id=DEMO_FRAUD_MERCHANT,
            mcc="7995",
            risk_score=0.92,
            country="MT",
            fraud_rate_30d=0.55,
            high_risk=True,
        ),
        # Risky merchant: high_risk (+0.30) + fraud_rate 0.20 (+0.20) -> score
        # ~0.55-0.70 -> exemption NONE -> SCA (step-up authentication).
        DEMO_RISKY_MERCHANT: MerchantFeatures(
            merchant_id=DEMO_RISKY_MERCHANT,
            mcc="7995",
            risk_score=0.66,
            country="CW",
            fraud_rate_30d=0.20,
            high_risk=True,
        ),
        # Clean merchant: very low acquirer fraud rate -> TRA-eligible for low
        # ECOM amounts -> APPROVE with a PSD2 exemption.
        DEMO_CLEAN_MERCHANT: MerchantFeatures(
            merchant_id=DEMO_CLEAN_MERCHANT,
            mcc="5411",
            risk_score=0.05,
            country="SE",
            fraud_rate_30d=0.0005,
            high_risk=False,
        ),
    }
