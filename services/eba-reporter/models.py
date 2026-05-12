"""Pydantic data contracts for the EBA/GL/2020/01 quarterly fraud report.

The EBA Guidelines on fraud reporting under PSD2 (EBA/GL/2020/01) require
PSPs to report aggregated payment-fraud statistics quarterly to their NCA,
broken down by:

    * payment instrument (card, credit transfer, direct debit, e-money, cash withdrawal)
    * remote vs non-remote
    * SCA applied (yes/no) and, when not applied, the exemption used
    * initiation channel (PISP / non-PISP)
    * fraud type (issuance of a payment order by the fraudster, modification by the
      fraudster, manipulation of the payer)
    * counterparty geography (EEA / non-EEA)
    * losses borne by (PSP / payer / other)

This module models a single reporting period for a single reporting PSP and
country (the platform reports per Nordic-Baltic country: SE/NO/DK/FI/EE).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Enumerations mirroring the EBA Annex tables
# ---------------------------------------------------------------------------


class Country(StrEnum):
    """ISO-3166 alpha-2 — limited to platform sovereignty scope."""

    SE = "SE"
    NO = "NO"
    DK = "DK"
    FI = "FI"
    EE = "EE"


class Instrument(StrEnum):
    """EBA Annex 1 — payment instrument categories."""

    CARD = "card"
    CREDIT_TRANSFER = "credit_transfer"
    DIRECT_DEBIT = "direct_debit"
    EMONEY = "e_money"
    CASH_WITHDRAWAL = "cash_withdrawal"


class Channel(StrEnum):
    """Remote vs non-remote initiation."""

    REMOTE = "remote"
    NON_REMOTE = "non_remote"


class ScaExemption(StrEnum):
    """RTS Art. 10–18 SCA exemptions (and the "applied" sentinel)."""

    APPLIED = "sca_applied"
    LOW_VALUE = "low_value"           # Art. 16
    TRA = "tra"                        # Art. 18 — transaction risk analysis
    TRUSTED_BENEFICIARY = "trusted"   # Art. 13
    RECURRING = "recurring"           # Art. 14
    CORPORATE = "corporate"           # Art. 17
    SECURE_CORPORATE = "secure_corp"  # Art. 17
    MERCHANT_INITIATED = "mit"        # MIT outside PSD2 scope
    CONTACTLESS_LOW_VALUE = "contactless_lv"  # Art. 11
    UNATTENDED_TRANSPORT = "unattended"        # Art. 12


class FraudType(StrEnum):
    """EBA Annex 3 — fraud typology."""

    ISSUANCE_BY_FRAUDSTER = "unauthorised_issuance"
    MODIFICATION_BY_FRAUDSTER = "unauthorised_modification"
    MANIPULATION_OF_PAYER = "manipulation_of_payer"
    LOST_STOLEN = "lost_stolen"
    CARD_NOT_RECEIVED = "card_not_received"
    COUNTERFEIT = "counterfeit"
    OTHER = "other"


class LossBearer(StrEnum):
    """Who bore the loss (Annex 4)."""

    PSP = "psp"
    PAYER = "payer"
    OTHER = "other"


class CounterpartyGeo(StrEnum):
    """Counterparty geography flag."""

    EEA = "eea"
    NON_EEA = "non_eea"


# ---------------------------------------------------------------------------
# Source records (silver layer rows)
# ---------------------------------------------------------------------------


class AggregatedFraudRow(BaseModel):
    """One row of the silver aggregate `gold.eba_report_q` table.

    Each row is the count and value of transactions for a single dimensional
    combination over the reporting quarter.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reporting_country: Country
    quarter: str = Field(pattern=r"^\d{4}-Q[1-4]$")
    instrument: Instrument
    channel: Channel
    sca_exemption: ScaExemption
    fraud_type: FraudType | None = None  # None = non-fraudulent baseline row
    counterparty_geo: CounterpartyGeo
    loss_bearer: LossBearer | None = None  # None when not fraud
    pisp_initiated: bool = False

    tx_count: int = Field(ge=0)
    tx_value_eur: Decimal = Field(ge=0)
    fraud_count: int = Field(ge=0)
    fraud_value_eur: Decimal = Field(ge=0)
    loss_value_eur: Decimal = Field(ge=0)

    @field_validator("fraud_count")
    @classmethod
    def _fraud_le_tx(cls, v: int, info) -> int:  # type: ignore[no-untyped-def]
        tx_count = info.data.get("tx_count", 0)
        if v > tx_count:
            raise ValueError("fraud_count cannot exceed tx_count")
        return v


# ---------------------------------------------------------------------------
# Output report
# ---------------------------------------------------------------------------


class ReportHeader(BaseModel):
    """Header block emitted in JSON & first sheet of the XLSX."""

    model_config = ConfigDict(extra="forbid")

    psp_lei: str = Field(min_length=20, max_length=20, description="LEI of reporting PSP")
    psp_name: str
    reporting_country: Country
    quarter: str
    period_start: date
    period_end: date
    submission_id: str
    eba_guideline: Literal["EBA/GL/2020/01"] = "EBA/GL/2020/01"
    schema_version: Literal["1.2"] = "1.2"


class ReportSection(BaseModel):
    """One Annex table aggregated for the report."""

    model_config = ConfigDict(extra="forbid")

    annex: Literal["A", "B", "C", "D"]
    title: str
    rows: list[dict[str, str | int | float]]


class EbaReport(BaseModel):
    """Full report payload — serialised to JSON next to the XLSX."""

    model_config = ConfigDict(extra="forbid")

    header: ReportHeader
    sections: list[ReportSection]
    totals: dict[str, float]
