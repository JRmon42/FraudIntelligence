from __future__ import annotations

from decimal import Decimal

import pytest

from models import (
    AggregatedFraudRow,
    Channel,
    CounterpartyGeo,
    Country,
    Instrument,
    ScaExemption,
)


def test_quarter_pattern_validates() -> None:
    with pytest.raises(ValueError):
        AggregatedFraudRow(
            reporting_country=Country.SE,
            quarter="2025Q1",  # missing dash
            instrument=Instrument.CARD,
            channel=Channel.REMOTE,
            sca_exemption=ScaExemption.APPLIED,
            counterparty_geo=CounterpartyGeo.EEA,
            tx_count=1,
            tx_value_eur=Decimal("1"),
            fraud_count=0,
            fraud_value_eur=Decimal("0"),
            loss_value_eur=Decimal("0"),
        )


def test_fraud_count_cannot_exceed_tx_count() -> None:
    with pytest.raises(ValueError, match="fraud_count cannot exceed"):
        AggregatedFraudRow(
            reporting_country=Country.SE,
            quarter="2025-Q1",
            instrument=Instrument.CARD,
            channel=Channel.REMOTE,
            sca_exemption=ScaExemption.APPLIED,
            counterparty_geo=CounterpartyGeo.EEA,
            tx_count=10,
            tx_value_eur=Decimal("100"),
            fraud_count=20,
            fraud_value_eur=Decimal("200"),
            loss_value_eur=Decimal("0"),
        )
