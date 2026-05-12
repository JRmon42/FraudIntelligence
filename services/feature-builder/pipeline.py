"""Pure async pipeline: dedup → fold card+merchant state → emit feature event.

Kept independent from the Azure Functions trigger so it is fully testable
without the `azure-functions` runtime.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from features_core import (
    TxnEvent,
    WindowState,
    build_feature_event,
    fold_event,
    parse_event,
)
from storage import EventEmitter, FeatureStore, get_dedup_ttl

log = structlog.get_logger(__name__)


def decode_event_body(body: bytes | str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(body, dict):
        return body
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    return json.loads(body)


async def _fold_one(
    store: FeatureStore, entity_type: str, entity_id: str, event: TxnEvent
) -> dict[str, float | int]:
    key = f"{entity_type}:{entity_id}"
    doc = await store.get_state(key)
    if doc is None:
        state = WindowState(entity_type=entity_type, entity_id=entity_id)  # type: ignore[arg-type]
    else:
        state = WindowState.from_doc(doc)
    new_state, feats = fold_event(state, event)
    await store.upsert_state(new_state.to_doc(feats))
    return feats


async def process_event(
    raw_body: bytes | str | dict[str, Any],
    store: FeatureStore,
    emitter: EventEmitter,
    dedup_ttl_s: int | None = None,
) -> dict[str, Any] | None:
    """Process one EH event. Returns the emitted feature payload, or None if duplicate."""

    payload = decode_event_body(raw_body)
    try:
        event = parse_event(payload)
    except (KeyError, ValueError, TypeError) as exc:
        log.warning("invalid_txn_event", err=str(exc), body=str(payload)[:200])
        return None

    if await store.seen(event.transaction_id):
        log.info("duplicate_event_skipped", transaction_id=event.transaction_id)
        return None

    card_feats = await _fold_one(store, "card", event.card_id, event)
    merchant_feats = await _fold_one(store, "merchant", event.merchant_id, event)
    feature_event = build_feature_event(event, card_feats, merchant_feats)
    await emitter.emit(feature_event)

    await store.mark_seen(event.transaction_id, dedup_ttl_s or get_dedup_ttl())
    log.info(
        "features_built",
        transaction_id=event.transaction_id,
        card_count_1h=card_feats.get("count_1h"),
        merchant_count_1h=merchant_feats.get("count_1h"),
    )
    return feature_event


async def process_batch(
    bodies: list[bytes | str | dict[str, Any]],
    store: FeatureStore,
    emitter: EventEmitter,
    dedup_ttl_s: int | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in bodies:
        result = await process_event(b, store, emitter, dedup_ttl_s)
        if result is not None:
            out.append(result)
    return out
