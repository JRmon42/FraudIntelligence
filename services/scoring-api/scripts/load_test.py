"""Locust driver targeting 5 000 TPS against POST /v1/score.

Configuration only — not run in CI.

Usage:
    locust -f scripts/load_test.py --host=http://localhost:8080 \
        --users 5000 --spawn-rate 500 --run-time 5m --headless

Each Locust user issues a synthetic transaction every ~1 s, so 5 000 users ≈ 5 k TPS.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

from locust import FastHttpUser, between, task

CHANNELS = ("ECOM", "POS", "MOTO", "ATM")
COUNTRIES = ("SE", "NO", "DK", "FI", "EE")
CURRENCIES = ("EUR", "SEK", "NOK", "DKK")
CARD_POOL = [f"card_{i:05d}" for i in range(10_000)]
MERCHANT_POOL = [f"mrc_{i:04d}" for i in range(2_000)]


class ScoringUser(FastHttpUser):
    """Synthetic merchant/issuer client."""

    wait_time = between(0.9, 1.1)

    @task
    def score(self) -> None:
        body = {
            "transaction_id": f"txn_{uuid.uuid4().hex[:16]}",
            "card_id": random.choice(CARD_POOL),
            "merchant_id": random.choice(MERCHANT_POOL),
            "amount": round(random.uniform(1.0, 950.0), 2),
            "currency": random.choice(CURRENCIES),
            "country": random.choice(COUNTRIES),
            "channel": random.choice(CHANNELS),
            "timestamp": datetime.now(UTC).isoformat(),
            "device_fingerprint": f"fp_{uuid.uuid4().hex[:12]}",
            "ip": f"203.0.113.{random.randint(1, 254)}",
        }
        with self.client.post(
            "/v1/score",
            json=body,
            name="POST /v1/score",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"status={r.status_code}")
            elif r.elapsed.total_seconds() * 1000 > 30:
                r.failure("latency budget exceeded (>30 ms)")
