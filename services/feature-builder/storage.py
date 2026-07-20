"""Persistence layer: Cosmos features container + dedup container, with in-memory fakes."""

from __future__ import annotations

import os
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)


class FeatureStore(Protocol):
    """Storage abstraction so tests can swap in an in-memory fake."""

    async def get_state(self, entity_key: str) -> dict[str, Any] | None: ...
    async def upsert_state(self, doc: dict[str, Any]) -> None: ...
    async def seen(self, transaction_id: str) -> bool: ...
    async def mark_seen(self, transaction_id: str, ttl_s: int) -> None: ...
    async def close(self) -> None: ...


class CosmosFeatureStore:
    """Real Cosmos implementation. Lazy-imports to keep test runs lightweight."""

    def __init__(
        self,
        endpoint: str,
        database: str,
        features_container: str,
        dedup_container: str,
        key: str | None = None,
    ) -> None:
        from azure.cosmos.aio import CosmosClient

        if key:
            self._client = CosmosClient(endpoint, credential=key)
        else:
            from azure.identity.aio import DefaultAzureCredential

            self._cred = DefaultAzureCredential()
            self._client = CosmosClient(endpoint, credential=self._cred)
        db = self._client.get_database_client(database)
        self._features = db.get_container_client(features_container)
        self._dedup = db.get_container_client(dedup_container)

    async def get_state(self, entity_key: str) -> dict[str, Any] | None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        try:
            return await self._features.read_item(item=entity_key, partition_key=entity_key)
        except CosmosResourceNotFoundError:
            return None

    async def upsert_state(self, doc: dict[str, Any]) -> None:
        await self._features.upsert_item(doc)

    async def seen(self, transaction_id: str) -> bool:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        try:
            await self._dedup.read_item(item=transaction_id, partition_key=transaction_id)
            return True
        except CosmosResourceNotFoundError:
            return False

    async def mark_seen(self, transaction_id: str, ttl_s: int) -> None:
        await self._dedup.upsert_item({"id": transaction_id, "ttl": ttl_s})

    async def close(self) -> None:
        await self._client.close()
        cred = getattr(self, "_cred", None)
        if cred is not None:
            await cred.close()


class InMemoryFeatureStore:
    """Test/dev fake with the same surface area as CosmosFeatureStore."""

    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {}
        self.dedup: set[str] = set()
        self.upserts: int = 0

    async def get_state(self, entity_key: str) -> dict[str, Any] | None:
        doc = self.states.get(entity_key)
        return None if doc is None else dict(doc)

    async def upsert_state(self, doc: dict[str, Any]) -> None:
        self.states[doc["entity_key"]] = dict(doc)
        self.upserts += 1

    async def seen(self, transaction_id: str) -> bool:
        return transaction_id in self.dedup

    async def mark_seen(self, transaction_id: str, ttl_s: int) -> None:  # noqa: ARG002
        self.dedup.add(transaction_id)

    async def close(self) -> None:
        return None


class EventEmitter(Protocol):
    async def emit(self, payload: dict[str, Any]) -> None: ...
    async def close(self) -> None: ...


class EventHubFeatureEmitter:
    """Producer for `feature.events`."""

    def __init__(self, conn_str: str, eventhub_name: str) -> None:
        from azure.eventhub.aio import EventHubProducerClient

        self._client = EventHubProducerClient.from_connection_string(
            conn_str, eventhub_name=eventhub_name
        )

    async def emit(self, payload: dict[str, Any]) -> None:
        import json

        from azure.eventhub import EventData

        try:
            batch = await self._client.create_batch()
            batch.add(EventData(json.dumps(payload, separators=(",", ":")).encode("utf-8")))
            await self._client.send_batch(batch)
        except Exception as exc:  # noqa: BLE001
            log.warning("feature_event_emit_failed", err=str(exc))

    async def close(self) -> None:
        await self._client.close()


class InMemoryEmitter:
    """Test fake — captures emitted feature events."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, payload: dict[str, Any]) -> None:
        self.events.append(payload)

    async def close(self) -> None:
        return None


def get_dedup_ttl() -> int:
    return int(os.getenv("FEATURE_BUILDER_DEDUP_TTL_S", "3600"))
