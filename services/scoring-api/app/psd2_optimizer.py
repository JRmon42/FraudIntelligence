"""PSD2 SCA exemption optimiser (rule + ML hybrid).

Picks the most beneficial *applicable* exemption to maximise frictionless
checkout rate while remaining compliant with EBA RTS on SCA.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import CardFeatures, MerchantFeatures, PSD2Exemption, ScoreRequest

# Low-value remote electronic payment thresholds (Article 16 RTS on SCA).
LOW_VALUE_AMOUNT_EUR = 30.0
LOW_VALUE_CUMULATIVE_AMOUNT_EUR = 100.0
LOW_VALUE_MAX_COUNT = 5

# Transaction Risk Analysis exemption tiers (Article 18 RTS on SCA).
TRA_TIERS: tuple[tuple[float, float], ...] = (
    # (max_amount_eur, max_acquirer_fraud_rate)
    (100.0, 0.0013),
    (250.0, 0.0006),
    (500.0, 0.0001),
)

NON_EEA_COUNTRIES_FOR_EXEMPTION: frozenset[str] = frozenset(
    # PSD2 SCA exemptions only apply when both PSPs are in the EEA.
    {"US", "GB", "CH", "JP", "CN", "RU", "BR", "IN"}
)


@dataclass(frozen=True)
class ExemptionContext:
    """Inputs the optimiser needs beyond the raw transaction request."""

    request: ScoreRequest
    card: CardFeatures | None
    merchant: MerchantFeatures | None
    cumulative_amount_eur: float = 0.0
    cumulative_count: int = 0
    score: float = 0.0


def _eea_eligible(country: str) -> bool:
    return country.upper() not in NON_EEA_COUNTRIES_FOR_EXEMPTION


def _amount_eur(req: ScoreRequest) -> float:
    # Simple proxy: assume already EUR or close enough for exemption gating.
    # Real implementation would call the FX service.
    if req.currency.upper() == "EUR":
        return req.amount
    return req.amount  # caller should pre-convert; we keep it deterministic here.


def is_low_value_eligible(ctx: ExemptionContext) -> bool:
    req = ctx.request
    if req.channel != "ECOM":
        return False
    if not _eea_eligible(req.country):
        return False
    amount = _amount_eur(req)
    if amount > LOW_VALUE_AMOUNT_EUR:
        return False
    if ctx.cumulative_amount_eur + amount > LOW_VALUE_CUMULATIVE_AMOUNT_EUR:
        return False
    if ctx.cumulative_count >= LOW_VALUE_MAX_COUNT:
        return False
    return True


def is_tra_eligible(ctx: ExemptionContext) -> bool:
    req = ctx.request
    if req.channel != "ECOM":
        return False
    if not _eea_eligible(req.country):
        return False
    if ctx.merchant is None:
        return False
    if ctx.merchant.high_risk:
        return False
    amount = _amount_eur(req)
    fraud_rate = ctx.merchant.fraud_rate_30d
    for max_amount, max_rate in TRA_TIERS:
        if amount <= max_amount and fraud_rate <= max_rate:
            return True
    return False


def is_trusted_beneficiary(ctx: ExemptionContext) -> bool:
    card = ctx.card
    merchant = ctx.merchant
    if card is None or merchant is None:
        return False
    # Stub: in production this comes from issuer's whitelist.
    return card.customer_segment == "trusted" and not merchant.high_risk


def is_corporate(ctx: ExemptionContext) -> bool:
    return bool(ctx.card and ctx.card.customer_segment == "corporate")


def select_exemption(ctx: ExemptionContext) -> PSD2Exemption:
    """Pick the best applicable exemption, skipping when score is too high."""

    # If model judges the transaction too risky, do not claim any exemption.
    if ctx.score >= 0.5:
        return "NONE"

    # Order: prefer the strongest legal protection for the merchant first.
    if is_corporate(ctx):
        return "CORPORATE"
    if is_trusted_beneficiary(ctx):
        return "TRUSTED_BENEFICIARY"
    if is_tra_eligible(ctx):
        return "TRA"
    if is_low_value_eligible(ctx):
        return "LOW_VALUE"
    return "NONE"


def decide(score: float, exemption: PSD2Exemption, card: CardFeatures | None) -> str:
    """Map (score, exemption, card-state) → APPROVE / SCA / DECLINE."""

    if card is not None and card.is_blocked:
        return "DECLINE"
    if score >= 0.85:
        return "DECLINE"
    if score >= 0.35 and exemption == "NONE":
        return "SCA"
    return "APPROVE"


def build_reason_codes(score: float, exemption: PSD2Exemption, ctx: ExemptionContext) -> list[str]:
    codes: list[str] = []
    if ctx.card and ctx.card.is_blocked:
        codes.append("CARD_BLOCKED")
    if score >= 0.85:
        codes.append("HIGH_RISK_SCORE")
    elif score >= 0.35:
        codes.append("MEDIUM_RISK_SCORE")
    else:
        codes.append("LOW_RISK")
    if ctx.merchant and ctx.merchant.high_risk:
        codes.append("MERCHANT_HIGH_RISK")
    if exemption != "NONE":
        codes.append(f"PSD2_{exemption}")
    return codes
