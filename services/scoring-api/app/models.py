"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["APPROVE", "SCA", "DECLINE"]
PSD2Exemption = Literal["TRA", "LOW_VALUE", "TRUSTED_BENEFICIARY", "CORPORATE", "NONE"]
Channel = Literal["ECOM", "POS", "MOTO", "ATM"]


class ScoreRequest(BaseModel):
    """Inbound transaction to be scored."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(min_length=1, max_length=64)
    card_id: str = Field(min_length=1, max_length=64)
    merchant_id: str = Field(min_length=1, max_length=64)
    amount: float = Field(ge=0.0)
    currency: str = Field(min_length=3, max_length=3)
    country: str = Field(min_length=2, max_length=2)
    channel: Channel
    timestamp: datetime
    device_fingerprint: str = Field(min_length=1, max_length=128)
    ip: str = Field(min_length=1, max_length=64)


class StageTimings(BaseModel):
    """Per-stage latency in milliseconds (returned with explain=true)."""

    features_ms: float
    aggregates_ms: float
    inference_ms: float
    psd2_ms: float
    emit_ms: float


class ScoreResponse(BaseModel):
    """Scoring result returned to the caller."""

    decision: Decision
    score: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str]
    psd2_exemption: PSD2Exemption
    model_version: str
    latency_ms: float
    explain: StageTimings | None = None


class CardFeatures(BaseModel):
    """Feature record stored in Cosmos `cards` container."""

    card_id: str
    risk_tier: int = Field(ge=0, le=5, default=0)
    avg_ticket: float = 0.0
    issue_country: str = ""
    chargebacks_30d: int = 0
    is_blocked: bool = False
    customer_segment: str = "retail"
    card_age_days: int = 800
    card_brand: str = "VISA"


class MerchantFeatures(BaseModel):
    """Feature record stored in Cosmos `merchants` container."""

    merchant_id: str
    mcc: str = "0000"
    risk_score: float = 0.0
    country: str = ""
    fraud_rate_30d: float = 0.0
    high_risk: bool = False


class Aggregates(BaseModel):
    """Real-time rolling aggregates pulled from Redis."""

    amount_1h: float = 0.0
    count_1h: int = 0
    declined_1h: int = 0
