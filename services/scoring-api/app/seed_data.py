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
DEMO_RING_CARD = "card-ring-099"         # high GNN ring_score -> GNN-driven SCA/DECLINE
DEMO_RING_CARDS = ["card-ring-099", "card-ring-100", "card-ring-101"]
DEMO_FRAUD_MERCHANT = "merch-darkbazaar-66"  # high-risk + high fraud rate -> DECLINE
DEMO_RISKY_MERCHANT = "merch-luckyspin-21"   # high-risk, medium fraud rate -> SCA
DEMO_CLEAN_MERCHANT = "merch-nordstore-5"    # low fraud rate -> TRA exemption (APPROVE)

# Centroid of the GraphSAGE embeddings of the true ring cards (ring_score > 0.8)
# from the latest ml/train_gnn.py run. Seeding the demo ring cards with this
# vector + a high ring_score makes the GNN signal flow through the ensemble so an
# ordinary small-hours transaction on these cards is stepped up / declined while
# the identical transaction on a random card is approved.
DEMO_RING_EMBEDDING = [
    0.6647, -1.1967, 0.0916, 0.2290, -2.5663, 1.1260, 1.3330, -0.9057,
    0.8630, -1.0388, -2.3975, 0.7887, 1.1515, -1.0082, -0.9796, -1.5087,
]


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
        # Ring cards: flagged by the fraud-ring GNN (high ring_score + ring-cluster
        # embedding). The ensemble consumes those GNN features, so an ordinary
        # small-hours transaction on these cards is stepped up / declined — the
        # GNN genuinely driving the live decision (an identical transaction on a
        # random card is approved). ring_score varies slightly per card.
        **{
            cid: CardFeatures(
                card_id=cid,
                risk_tier=2,
                avg_ticket=300.0,
                issue_country="SE",
                chargebacks_30d=1,
                is_blocked=False,
                customer_segment="retail",
                ring_score=rs,
                gnn_embedding=DEMO_RING_EMBEDDING,
            )
            for cid, rs in zip(DEMO_RING_CARDS, (0.97, 0.95, 0.96))
        },
    }


def demo_aggregates() -> dict[str, dict[str, float]]:
    """Rolling 1-hour aggregates seeded into Redis for the demo cards.

    With Azure Managed Redis now in the live path, ``AggregatesStore`` reads
    real velocity signals from the cache. Seeding a curated set makes those
    reads meaningful for the demo: the ring / hot / blocked cards show elevated
    velocity and recent declines, reinforcing the SCA / DECLINE decisions while
    ordinary cards keep their empty (near-zero) aggregates.
    """

    agg = {
        DEMO_HOT_CARD: {"amount_1h": 1180.0, "count_1h": 5, "declined_1h": 3},
        DEMO_BLOCKED_CARD: {"amount_1h": 520.0, "count_1h": 2, "declined_1h": 1},
    }
    # Ring cards: fast cash-out velocity within the hour.
    for cid in DEMO_RING_CARDS:
        agg[cid] = {"amount_1h": 2840.0, "count_1h": 9, "declined_1h": 2}
    return agg


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
