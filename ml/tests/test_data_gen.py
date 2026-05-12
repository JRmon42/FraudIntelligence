"""Smoke tests for the synthetic data generator."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.data.synthetic_data import SyntheticConfig, generate, NORDIC_COUNTRIES


def test_generate_basic_shape():
    df = generate(SyntheticConfig(n_transactions=2_000, seed=1))
    assert len(df) >= 2_000  # rings add extra rows
    expected_cols = {"tx_id", "card_id", "merchant_id", "device_id", "ip_id",
                     "amount", "is_fraud", "card_country", "ip_country", "mcc"}
    assert expected_cols.issubset(set(df.columns))
    assert df["is_fraud"].dtype.kind == "i"


def test_country_distribution():
    df = generate(SyntheticConfig(n_transactions=5_000, seed=2))
    countries = set(df["card_country"].unique())
    # Every Nordic country should be represented
    assert set(NORDIC_COUNTRIES).issubset(countries)


def test_fraud_rings_present():
    df = generate(SyntheticConfig(n_transactions=3_000, seed=3))
    assert (df["ring_id"] != "").any(), "ring patterns should be injected"
    rings = df.loc[df["ring_id"] != ""]
    # All ring transactions are labelled fraud
    assert (rings["is_fraud"] == 1).all()


def test_deterministic_with_seed():
    a = generate(SyntheticConfig(n_transactions=1_000, seed=7))
    b = generate(SyntheticConfig(n_transactions=1_000, seed=7))
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))
