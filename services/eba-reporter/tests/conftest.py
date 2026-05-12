"""Shared pytest fixtures for the eba-reporter test suite."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from models import (  # noqa: E402
    AggregatedFraudRow,
    Channel,
    CounterpartyGeo,
    Country,
    FraudType,
    Instrument,
    LossBearer,
    ScaExemption,
)


@pytest.fixture
def sample_rows() -> list[AggregatedFraudRow]:
    """Synthetic fixture covering the full EBA dimensional cube (small slice)."""
    return [
        AggregatedFraudRow(
            reporting_country=Country.SE,
            quarter="2025-Q1",
            instrument=Instrument.CARD,
            channel=Channel.REMOTE,
            sca_exemption=ScaExemption.TRA,
            fraud_type=FraudType.MANIPULATION_OF_PAYER,
            counterparty_geo=CounterpartyGeo.EEA,
            loss_bearer=LossBearer.PSP,
            tx_count=10_000,
            tx_value_eur=Decimal("5000000.00"),
            fraud_count=12,
            fraud_value_eur=Decimal("6500.00"),
            loss_value_eur=Decimal("4200.00"),
        ),
        AggregatedFraudRow(
            reporting_country=Country.SE,
            quarter="2025-Q1",
            instrument=Instrument.CARD,
            channel=Channel.REMOTE,
            sca_exemption=ScaExemption.APPLIED,
            fraud_type=None,
            counterparty_geo=CounterpartyGeo.EEA,
            loss_bearer=None,
            tx_count=200_000,
            tx_value_eur=Decimal("80000000.00"),
            fraud_count=0,
            fraud_value_eur=Decimal("0"),
            loss_value_eur=Decimal("0"),
        ),
        AggregatedFraudRow(
            reporting_country=Country.SE,
            quarter="2025-Q1",
            instrument=Instrument.CREDIT_TRANSFER,
            channel=Channel.REMOTE,
            sca_exemption=ScaExemption.LOW_VALUE,
            fraud_type=FraudType.ISSUANCE_BY_FRAUDSTER,
            counterparty_geo=CounterpartyGeo.NON_EEA,
            loss_bearer=LossBearer.PAYER,
            tx_count=50_000,
            tx_value_eur=Decimal("1500000.00"),
            fraud_count=3,
            fraud_value_eur=Decimal("210.00"),
            loss_value_eur=Decimal("210.00"),
        ),
    ]
