"""Fire-and-forget Event Hubs producer for decision events."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

import structlog
from azure.eventhub import EventData
from azure.eventhub.aio import EventHubProducerClient
from azure.identity.aio import DefaultAzureCredential

from .settings import Settings

log = structlog.get_logger(__name__)


class DecisionEmitter(Protocol):
    async def emit(self, payload: dict[str, Any]) -> None: ...
    async def close(self) -> None: ...
    @property
    def healthy(self) -> bool: ...


class EventHubsDecisionEmitter:
    """Async producer for `decision.events`. Failures never block the hot path."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._producer: EventHubProducerClient | None = None
        self._credential: DefaultAzureCredential | None = None
        self._healthy = False

    async def connect(self) -> None:
        if self._producer is not None:
            return
        if not self._settings.eventhub_fqdn and not self._settings.eventhub_conn_str:
            log.warning("eventhub_unconfigured", note="decision events will be no-op")
            return
        try:
            if self._settings.eventhub_conn_str:
                self._producer = EventHubProducerClient.from_connection_string(
                    self._settings.eventhub_conn_str,
                    eventhub_name=self._settings.eventhub_decisions,
                )
            else:
                self._credential = DefaultAzureCredential()
                self._producer = EventHubProducerClient(
                    fully_qualified_namespace=self._settings.eventhub_fqdn,
                    eventhub_name=self._settings.eventhub_decisions,
                    credential=self._credential,
                )
            self._healthy = True
            log.info("eventhub_producer_ready", hub=self._settings.eventhub_decisions)
        except Exception as exc:  # noqa: BLE001
            log.error("eventhub_producer_init_failed", err=str(exc))
            self._healthy = False

    async def close(self) -> None:
        if self._producer is not None:
            try:
                await self._producer.close()
            except Exception:  # noqa: BLE001, S110
                pass
            self._producer = None
        if self._credential is not None:
            await self._credential.close()
            self._credential = None
        self._healthy = False

    @property
    def healthy(self) -> bool:
        return self._healthy

    async def emit(self, payload: dict[str, Any]) -> None:
        """Schedule a fire-and-forget send; returns immediately."""

        if self._producer is None:
            return
        asyncio.create_task(self._send(payload))

    async def _send(self, payload: dict[str, Any]) -> None:
        try:
            assert self._producer is not None
            batch = await self._producer.create_batch()
            batch.add(EventData(json.dumps(payload, separators=(",", ":")).encode("utf-8")))
            await self._producer.send_batch(batch)
        except Exception as exc:  # noqa: BLE001 - producer failure must not affect caller
            log.warning("eventhub_emit_failed", err=str(exc))


class NullDecisionEmitter:
    """Used in tests / when Event Hubs is unconfigured."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._healthy = True

    @property
    def healthy(self) -> bool:
        return self._healthy

    def fail(self) -> None:
        self._healthy = False

    async def emit(self, payload: dict[str, Any]) -> None:
        if not self._healthy:
            log.warning("eventhub_emit_failed_simulated")
            return
        self.events.append(payload)

    async def close(self) -> None:
        return None
