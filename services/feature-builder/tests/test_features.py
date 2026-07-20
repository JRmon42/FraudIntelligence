"""Tests for the feature-builder pipeline using in-memory fakes."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from features_core import (
    WINDOWS_S,
    WindowState,
    compute_features,
    parse_event,
    update_state,
)
from pipeline import process_batch, process_event
from storage import InMemoryEmitter, InMemoryFeatureStore

# ---------- factories ----------


class FakeEHEvent:
    """Mimics `azure.functions.EventHubEvent.get_body()`."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def get_body(self) -> bytes:
        return json.dumps(self._payload, default=str).encode("utf-8")


def make_event(
    *,
    transaction_id: str | None = None,
    card_id: str = "card_42",
    merchant_id: str = "mrc_99",
    amount: float = 25.0,
    currency: str = "EUR",
    timestamp: datetime | None = None,
) -> FakeEHEvent:
    return FakeEHEvent(
        {
            "transaction_id": transaction_id or f"txn_{uuid4().hex[:12]}",
            "card_id": card_id,
            "merchant_id": merchant_id,
            "amount": amount,
            "currency": currency,
            "timestamp": (timestamp or datetime.now(UTC)).isoformat(),
        }
    )


# ---------- features_core ----------


def test_parse_event_handles_iso_string() -> None:
    e = parse_event(
        {
            "transaction_id": "t1",
            "card_id": "c1",
            "merchant_id": "m1",
            "amount": "12.50",
            "currency": "EUR",
            "timestamp": "2025-05-12T10:00:00Z",
        }
    )
    assert e.amount == 12.50
    assert e.timestamp.tzinfo is not None


def test_compute_features_empty_state_returns_zeros() -> None:
    state = WindowState(entity_type="card", entity_id="c1")
    state.last_seen_iso = datetime(2025, 5, 12, tzinfo=UTC).isoformat()
    feats = compute_features(state)
    for label in WINDOWS_S:
        assert feats[f"count_{label}"] == 0
        assert feats[f"amount_{label}"] == 0.0


def test_update_and_compute_rolls_into_correct_windows() -> None:
    base = datetime(2025, 5, 12, 10, 0, 0, tzinfo=UTC)
    state = WindowState(entity_type="card", entity_id="c1")
    # Three events: 10s ago, 2 min ago, 2 hours ago.
    for offset_s, amount, mid in [
        (10, 10.0, "m1"),
        (120, 20.0, "m2"),
        (7200, 30.0, "m3"),
    ]:
        ev = parse_event(
            {
                "transaction_id": f"t{offset_s}",
                "card_id": "c1",
                "merchant_id": mid,
                "amount": amount,
                "timestamp": (base - timedelta(seconds=offset_s)).isoformat(),
            }
        )
        update_state(state, ev)

    feats = compute_features(state, now=base)
    assert feats["count_1m"] == 1 and feats["amount_1m"] == 10.0
    assert feats["count_5m"] == 2 and feats["amount_5m"] == 30.0
    assert feats["count_1h"] == 2 and feats["amount_1h"] == 30.0
    assert feats["count_24h"] == 3 and feats["amount_24h"] == 60.0
    assert feats["unique_merchants_1h"] == 2


def test_update_prunes_events_outside_24h() -> None:
    base = datetime(2025, 5, 12, 10, 0, 0, tzinfo=UTC)
    state = WindowState(entity_type="card", entity_id="c1")
    old = parse_event(
        {
            "transaction_id": "old",
            "card_id": "c1",
            "merchant_id": "m1",
            "amount": 5.0,
            "timestamp": (base - timedelta(days=2)).isoformat(),
        }
    )
    update_state(state, old)
    assert len(state.events) == 1

    fresh = parse_event(
        {
            "transaction_id": "new",
            "card_id": "c1",
            "merchant_id": "m1",
            "amount": 5.0,
            "timestamp": base.isoformat(),
        }
    )
    update_state(state, fresh)
    # Old event must be pruned (outside 24h relative to fresh).
    assert len(state.events) == 1


def test_window_state_doc_roundtrip() -> None:
    state = WindowState(entity_type="merchant", entity_id="m1")
    state.events = [(1.0, 10.0, "m1"), (2.0, 20.0, "m1")]
    state.last_seen_iso = "2025-05-12T10:00:00+00:00"
    doc = state.to_doc({"count_1h": 2, "amount_1h": 30.0})
    assert doc["id"] == "merchant:m1"
    restored = WindowState.from_doc(doc)
    assert restored.events == state.events


# ---------- pipeline ----------


@pytest.mark.asyncio
async def test_process_event_emits_feature_payload() -> None:
    store = InMemoryFeatureStore()
    emitter = InMemoryEmitter()
    ev = make_event(transaction_id="t1", amount=42.0)
    out = await process_event(ev.get_body(), store, emitter)
    assert out is not None
    assert out["transaction_id"] == "t1"
    assert out["card_features"]["count_1h"] == 1
    assert out["card_features"]["amount_1h"] == 42.0
    assert out["merchant_features"]["count_1h"] == 1
    assert len(emitter.events) == 1


@pytest.mark.asyncio
async def test_idempotency_skips_duplicate_transaction() -> None:
    store = InMemoryFeatureStore()
    emitter = InMemoryEmitter()
    ev = make_event(transaction_id="dup", amount=10.0)
    first = await process_event(ev.get_body(), store, emitter)
    second = await process_event(ev.get_body(), store, emitter)
    assert first is not None
    assert second is None
    assert len(emitter.events) == 1
    # And state should reflect only the first fold.
    assert store.states["card:card_42"]["features"]["count_1h"] == 1


@pytest.mark.asyncio
async def test_invalid_event_body_does_not_crash() -> None:
    store = InMemoryFeatureStore()
    emitter = InMemoryEmitter()
    out = await process_event(b'{"not":"valid"}', store, emitter)
    assert out is None
    assert emitter.events == []


@pytest.mark.asyncio
async def test_process_batch_aggregates_card_state_across_events() -> None:
    store = InMemoryFeatureStore()
    emitter = InMemoryEmitter()
    base = datetime(2025, 5, 12, 10, 0, 0, tzinfo=UTC)
    bodies = [
        make_event(
            transaction_id=f"t{i}",
            amount=10.0 * (i + 1),
            timestamp=base + timedelta(seconds=i),
        ).get_body()
        for i in range(3)
    ]
    out = await process_batch(bodies, store, emitter)
    assert len(out) == 3
    last = out[-1]
    assert last["card_features"]["count_1h"] == 3
    assert last["card_features"]["amount_1h"] == 60.0


@pytest.mark.asyncio
async def test_two_cards_keep_independent_state() -> None:
    store = InMemoryFeatureStore()
    emitter = InMemoryEmitter()
    await process_event(make_event(card_id="A", transaction_id="a1").get_body(), store, emitter)
    await process_event(make_event(card_id="B", transaction_id="b1").get_body(), store, emitter)
    assert store.states["card:A"]["features"]["count_1h"] == 1
    assert store.states["card:B"]["features"]["count_1h"] == 1
