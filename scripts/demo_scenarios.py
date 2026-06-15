#!/usr/bin/env python3
"""Curated decision scenarios for the Heimdall demo.

WHY THIS EXISTS
---------------
The deployed scoring API currently runs as a *stub* (no feature store / no ONNX
model wired in the Container App), so it APPROVEs every transaction at score
~0.2. That is great for showing latency/throughput, but it cannot show the
*decision spectrum* — DECLINE for fraud, and SCA step-up for borderline /
potential false positives.

This module reproduces the **exact decision logic** of the production scoring
service so the demo can show that spectrum honestly, using feature-enriched
demo transactions. The thresholds and rules here are a faithful, dependency-free
port of:
  * services/scoring-api/app/scoring.py        (_stub_score)
  * services/scoring-api/app/psd2_optimizer.py (select_exemption / decide /
                                                build_reason_codes)

Keep this in sync with those modules if the production rules change.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# --- PSD2 exemption thresholds (mirror psd2_optimizer.py) ------------------- #
LOW_VALUE_AMOUNT_EUR = 30.0
LOW_VALUE_CUMULATIVE_AMOUNT_EUR = 100.0
LOW_VALUE_MAX_COUNT = 5
TRA_TIERS = ((100.0, 0.0013), (250.0, 0.0006), (500.0, 0.0001))
NON_EEA_COUNTRIES_FOR_EXEMPTION = frozenset(
    {"US", "GB", "CH", "JP", "CN", "RU", "BR", "IN"}
)


@dataclass
class Card:
    card_id: str
    risk_tier: int = 0
    avg_ticket: float = 0.0
    issue_country: str = ""
    chargebacks_30d: int = 0
    is_blocked: bool = False
    customer_segment: str = "retail"


@dataclass
class Merchant:
    merchant_id: str
    mcc: str = "0000"
    risk_score: float = 0.0
    country: str = ""
    fraud_rate_30d: float = 0.0
    high_risk: bool = False


@dataclass
class Agg:
    amount_1h: float = 0.0
    count_1h: int = 0
    declined_1h: int = 0


@dataclass
class Scenario:
    key: str
    title: str
    narrative: str          # what the transaction represents
    handling: str           # how the platform handles the outcome
    amount: float
    currency: str
    country: str
    channel: str
    card: Card
    merchant: Merchant
    agg: Agg = field(default_factory=Agg)
    cumulative_amount_eur: float = 0.0
    cumulative_count: int = 0
    # When True, emit a follow-up "recovered" APPROVE row to show that a flagged
    # genuine customer clears the SCA challenge and the payment proceeds.
    recovers_after_sca: bool = False


# --------------------------------------------------------------------------- #
# Decision engine (faithful port of the production rules)
# --------------------------------------------------------------------------- #
def stub_score(s: Scenario) -> float:
    """Mirror of scoring._stub_score (same coefficients and hash jitter)."""
    card, merch, agg = s.card, s.merchant, s.agg
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
    if s.amount > 1000:
        base += 0.15
    if agg.declined_1h > 2:
        base += 0.20
    if agg.count_1h > 20:
        base += 0.10
    digest = hashlib.blake2b(
        f"{s.key}|{s.card.card_id}|{s.merchant.merchant_id}".encode(), digest_size=4
    ).digest()
    jitter = int.from_bytes(digest, "big") / 0xFFFFFFFF * 0.05
    return float(min(max(base + jitter, 0.0), 1.0))


def _eea_eligible(country: str) -> bool:
    return country.upper() not in NON_EEA_COUNTRIES_FOR_EXEMPTION


def _is_low_value(s: Scenario) -> bool:
    if s.channel != "ECOM" or not _eea_eligible(s.country):
        return False
    if s.amount > LOW_VALUE_AMOUNT_EUR:
        return False
    if s.cumulative_amount_eur + s.amount > LOW_VALUE_CUMULATIVE_AMOUNT_EUR:
        return False
    return s.cumulative_count < LOW_VALUE_MAX_COUNT


def _is_tra(s: Scenario) -> bool:
    if s.channel != "ECOM" or not _eea_eligible(s.country):
        return False
    if s.merchant is None or s.merchant.high_risk:
        return False
    for max_amount, max_rate in TRA_TIERS:
        if s.amount <= max_amount and s.merchant.fraud_rate_30d <= max_rate:
            return True
    return False


def select_exemption(s: Scenario, score: float) -> str:
    if score >= 0.5:
        return "NONE"
    if s.card and s.card.customer_segment == "corporate":
        return "CORPORATE"
    if s.card and s.merchant and s.card.customer_segment == "trusted" and not s.merchant.high_risk:
        return "TRUSTED_BENEFICIARY"
    if _is_tra(s):
        return "TRA"
    if _is_low_value(s):
        return "LOW_VALUE"
    return "NONE"


def decide(score: float, exemption: str, card: Card) -> str:
    if card is not None and card.is_blocked:
        return "DECLINE"
    if score >= 0.85:
        return "DECLINE"
    if score >= 0.35 and exemption == "NONE":
        return "SCA"
    return "APPROVE"


def reason_codes(score: float, exemption: str, s: Scenario) -> list[str]:
    codes: list[str] = []
    if s.card and s.card.is_blocked:
        codes.append("CARD_BLOCKED")
    if score >= 0.85:
        codes.append("HIGH_RISK_SCORE")
    elif score >= 0.35:
        codes.append("MEDIUM_RISK_SCORE")
    else:
        codes.append("LOW_RISK")
    if s.merchant and s.merchant.high_risk:
        codes.append("MERCHANT_HIGH_RISK")
    if s.agg.declined_1h > 2:
        codes.append("VELOCITY_DECLINES_1H")
    if exemption != "NONE":
        codes.append(f"PSD2_{exemption}")
    return codes


def evaluate(s: Scenario) -> dict:
    """Run the full pipeline for a scenario and return a result dict."""
    score = stub_score(s)
    exemption = select_exemption(s, score)
    decision = decide(score, exemption, s.card)
    return {
        "decision": decision,
        "score": round(score, 4),
        "psd2_exemption": exemption,
        "reason_codes": reason_codes(score, exemption, s),
    }


# --------------------------------------------------------------------------- #
# The curated scenario set — a clear, realistic decision spectrum
# --------------------------------------------------------------------------- #
SCENARIOS: list[Scenario] = [
    Scenario(
        key="groceries-lowvalue",
        title="Genuine groceries (low value)",
        narrative="A €24.90 online grocery order from a long-standing Swedish customer.",
        handling="Approved frictionlessly via the PSD2 low-value exemption — no challenge, "
                 "best possible checkout experience for a clearly genuine payment.",
        amount=24.90, currency="EUR", country="SE", channel="ECOM",
        card=Card("c-good-001", risk_tier=0, issue_country="SE", customer_segment="retail"),
        merchant=Merchant("m-grocer-001", mcc="5411", fraud_rate_30d=0.002, country="SE"),
    ),
    Scenario(
        key="trusted-tra",
        title="Trusted retailer (TRA exemption)",
        narrative="A €180 purchase at a low-fraud retailer the bank can risk-exempt under TRA.",
        handling="Approved frictionlessly via the PSD2 Transaction-Risk-Analysis exemption — "
                 "the acquirer's low fraud rate lets the bank skip the challenge while staying compliant.",
        amount=180.0, currency="EUR", country="SE", channel="ECOM",
        card=Card("c-good-014", risk_tier=1, issue_country="SE", customer_segment="retail"),
        merchant=Merchant("m-retail-007", mcc="5732", fraud_rate_30d=0.0005, country="SE"),
    ),
    Scenario(
        key="false-positive-stepup",
        title="Borderline payment → possible FALSE POSITIVE",
        narrative="An €850 electronics order. Mildly elevated risk (new-ish device, "
                  "moderate-fraud merchant) — could be the real customer, could be fraud.",
        handling="NOT blocked. The customer is challenged with Strong Customer Authentication "
                 "(3-D Secure). Genuine customers simply approve in their banking app and the "
                 "payment proceeds — this is how Heimdall protects real customers from being "
                 "wrongly declined (false-positive mitigation).",
        amount=850.0, currency="EUR", country="NO", channel="ECOM",
        card=Card("c-cust-220", risk_tier=3, chargebacks_30d=1, issue_country="NO",
                  customer_segment="retail"),
        merchant=Merchant("m-elec-031", mcc="5732", fraud_rate_30d=0.15, country="NO"),
        recovers_after_sca=True,
    ),
    Scenario(
        key="velocity-stepup",
        title="Unusual velocity → step-up",
        narrative="A €120 payment from a card that has seen many attempts and several "
                  "declines in the last hour.",
        handling="Stepped up to SCA on velocity signals. If it is the genuine cardholder, the "
                 "challenge clears it; if not, the fraudster cannot complete authentication.",
        amount=120.0, currency="EUR", country="FI", channel="ECOM",
        card=Card("c-cust-431", risk_tier=2, issue_country="FI", customer_segment="retail"),
        merchant=Merchant("m-shop-099", mcc="5999", fraud_rate_30d=0.05, country="FI"),
        agg=Agg(amount_1h=900.0, count_1h=24, declined_1h=4),
    ),
    Scenario(
        key="blocked-card-fraud",
        title="Confirmed fraud — blocked card",
        narrative="A €430 attempt on a card the issuer has already blocked (reported stolen).",
        handling="Hard DECLINE. An agentic fraud case is opened automatically (triage → "
                 "graph-analyst → policy → narrative), so analysts get a ready-to-action case.",
        amount=430.0, currency="EUR", country="SE", channel="ECOM",
        card=Card("c-stolen-777", risk_tier=4, issue_country="SE", is_blocked=True),
        merchant=Merchant("m-shop-012", mcc="5999", fraud_rate_30d=0.03, country="SE"),
    ),
    Scenario(
        key="ring-cashout-fraud",
        title="Fraud-ring cash-out — high risk",
        narrative="A €5,200 'purchase' that is really a ring cashing out: risky card, "
                  "high-risk merchant, large amount.",
        handling="Hard DECLINE on a high model score. The closed circular value-flow is also "
                 "flagged by the offline GNN on Fabric Spark, linking the whole ring for the case.",
        amount=5200.0, currency="EUR", country="SE", channel="ECOM",
        card=Card("ring-card-00", risk_tier=5, chargebacks_30d=5, issue_country="SE"),
        merchant=Merchant("ring-mer-00", mcc="6051", fraud_rate_30d=0.5, high_risk=True, country="SE"),
    ),
]


def scenario_summary() -> dict[str, int]:
    """Decision tally for the curated set — handy for tests/sanity checks."""
    tally: dict[str, int] = {}
    for s in SCENARIOS:
        d = evaluate(s)["decision"]
        tally[d] = tally.get(d, 0) + 1
    return tally


if __name__ == "__main__":
    # Quick self-check: print each scenario's decision.
    for sc in SCENARIOS:
        r = evaluate(sc)
        print(f"{sc.key:24s} {r['decision']:8s} score={r['score']:.3f} "
              f"exempt={r['psd2_exemption']:18s} {r['reason_codes']}")
    print("tally:", scenario_summary())
