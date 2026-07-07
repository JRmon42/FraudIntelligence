"""Tests for the Redis-backed AggregatesStore (fakeredis) and Entra token parsing."""

from __future__ import annotations

import base64
import json

import pytest

from app.features import AggregatesStore, _oid_from_token
from app.seed_data import DEMO_RING_CARDS, demo_aggregates
from app.settings import Settings


def _fake_jwt(oid: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"oid": oid}).encode()).decode().rstrip("=")
    return f"hdr.{payload}.sig"


def test_oid_from_token_reads_oid_claim() -> None:
    assert _oid_from_token(_fake_jwt("abc-123")) == "abc-123"


def test_oid_from_token_handles_garbage() -> None:
    assert _oid_from_token("not-a-jwt") == ""


@pytest.mark.asyncio
async def test_seed_demo_is_idempotent_and_readable() -> None:
    store = await AggregatesStore.create(Settings(redis_fake=True))

    written = await store.seed_demo()
    assert written == len(demo_aggregates())

    # Second run writes nothing (idempotent) and never overwrites live data.
    assert await store.seed_demo() == 0

    agg = await store.get_for_card(DEMO_RING_CARDS[0])
    assert agg.count_1h == 9
    assert agg.declined_1h == 2
    assert agg.amount_1h > 0

    # An unseeded card returns empty aggregates.
    empty = await store.get_for_card("card-unknown-999")
    assert empty.count_1h == 0
    await store.close()
