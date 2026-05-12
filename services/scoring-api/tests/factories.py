"""Helpers to build valid score-request payloads for tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def make_payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "transaction_id": "txn_test_001",
        "card_id": "card_ok",
        "merchant_id": "mrc_safe",
        "amount": 12.50,
        "currency": "EUR",
        "country": "SE",
        "channel": "ECOM",
        "timestamp": datetime(2025, 5, 12, 10, 0, 0, tzinfo=UTC).isoformat(),
        "device_fingerprint": "fp_abc",
        "ip": "203.0.113.7",
    }
    base.update(overrides)
    return base
