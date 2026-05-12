"""Azure Functions v2 entrypoint for the feature builder."""

from __future__ import annotations

import asyncio
import logging
import os

import azure.functions as func
import structlog

from pipeline import process_batch
from storage import (
    CosmosFeatureStore,
    EventEmitter,
    EventHubFeatureEmitter,
    FeatureStore,
    InMemoryEmitter,
    InMemoryFeatureStore,
    get_dedup_ttl,
)

logging.basicConfig(level=logging.INFO)
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger(__name__)

app = func.FunctionApp()

_STORE: FeatureStore | None = None
_EMITTER: EventEmitter | None = None
_LOCK = asyncio.Lock()


async def _get_store() -> FeatureStore:
    global _STORE
    if _STORE is not None:
        return _STORE
    async with _LOCK:
        if _STORE is not None:
            return _STORE
        endpoint = os.getenv("COSMOS_ENDPOINT", "")
        if not endpoint:
            log.warning("cosmos_unconfigured_using_inmemory")
            _STORE = InMemoryFeatureStore()
        else:
            _STORE = CosmosFeatureStore(
                endpoint=endpoint,
                database=os.getenv("COSMOS_DATABASE", "fraudintel"),
                features_container=os.getenv("COSMOS_FEATURES_CONTAINER", "features"),
                dedup_container=os.getenv("COSMOS_DEDUP_CONTAINER", "dedup"),
                key=os.getenv("COSMOS_KEY") or None,
            )
        return _STORE


async def _get_emitter() -> EventEmitter:
    global _EMITTER
    if _EMITTER is not None:
        return _EMITTER
    async with _LOCK:
        if _EMITTER is not None:
            return _EMITTER
        conn = os.getenv("EVENTHUB_FEATURE_CONN_STR", "")
        name = os.getenv("EVENTHUB_FEATURE_NAME", "feature.events")
        if not conn:
            log.warning("eventhub_feature_unconfigured_using_inmemory")
            _EMITTER = InMemoryEmitter()
        else:
            _EMITTER = EventHubFeatureEmitter(conn, name)
        return _EMITTER


@app.event_hub_message_trigger(
    arg_name="events",
    event_hub_name="%EVENTHUB_TXN_NAME%",
    connection="EVENTHUB_TXN_CONN_STR",
    consumer_group="%EVENTHUB_CONSUMER_GROUP%",
    cardinality=func.Cardinality.MANY,
)
async def feature_builder(events: list[func.EventHubEvent]) -> None:
    """Trigger entrypoint: turns a batch of EH events into feature events."""

    store = await _get_store()
    emitter = await _get_emitter()
    bodies = [e.get_body() for e in events]
    try:
        out = await process_batch(bodies, store, emitter, get_dedup_ttl())
    except Exception:  # noqa: BLE001
        log.exception("feature_builder_batch_failed", batch_size=len(bodies))
        raise
    log.info("feature_builder_batch_ok", batch_size=len(bodies), emitted=len(out))
