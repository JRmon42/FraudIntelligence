"""Fire-and-forget Service Bus publisher for high-risk enforcement alerts.

On a ``DECLINE`` (and other high-risk decisions) the synchronous scoring path
enqueues a message onto the ``highrisk-alerts`` Service Bus queue. The durable
enforcement action — block the card, open a case, notify the customer — is then
taken asynchronously by the enforcement Azure Function, keeping that work out of
the sub-20 ms scoring budget. Publishing is fire-and-forget: a Service Bus
failure logs a warning and never blocks or fails the caller.

Authentication is key-less (Entra ID / Managed Identity); the queue namespace
has ``disableLocalAuth=true``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

import structlog

from .settings import Settings

log = structlog.get_logger(__name__)


class AlertPublisher(Protocol):
    async def publish(self, payload: dict[str, Any]) -> None: ...
    async def close(self) -> None: ...
    @property
    def healthy(self) -> bool: ...


class ServiceBusAlertPublisher:
    """Async publisher for the ``highrisk-alerts`` queue. Never blocks the hot path."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None
        self._credential: Any | None = None
        self._healthy = False

    async def connect(self) -> None:
        if self._client is not None:
            return
        if not self._settings.servicebus_fqdn:
            log.warning("servicebus_unconfigured", note="enforcement alerts will be no-op")
            return
        try:
            from azure.identity.aio import DefaultAzureCredential
            from azure.servicebus.aio import ServiceBusClient

            self._credential = DefaultAzureCredential()
            self._client = ServiceBusClient(
                fully_qualified_namespace=self._settings.servicebus_fqdn,
                credential=self._credential,
            )
            self._healthy = True
            log.info(
                "servicebus_publisher_ready",
                namespace=self._settings.servicebus_fqdn,
                queue=self._settings.servicebus_queue,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("servicebus_publisher_init_failed", err=str(exc))
            self._healthy = False

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001, S110
                pass
            self._client = None
        if self._credential is not None:
            try:
                await self._credential.close()
            except Exception:  # noqa: BLE001, S110
                pass
            self._credential = None
        self._healthy = False

    @property
    def healthy(self) -> bool:
        return self._healthy

    async def publish(self, payload: dict[str, Any]) -> None:
        """Schedule a fire-and-forget send; returns immediately."""

        if self._client is None:
            return
        asyncio.create_task(self._send(payload))

    async def _send(self, payload: dict[str, Any]) -> None:
        try:
            from azure.servicebus import ServiceBusMessage

            assert self._client is not None
            body = json.dumps(payload, separators=(",", ":"))
            async with self._client.get_queue_sender(self._settings.servicebus_queue) as sender:
                await sender.send_messages(
                    ServiceBusMessage(
                        body,
                        content_type="application/json",
                        subject=payload.get("decision", "ALERT"),
                    )
                )
        except Exception as exc:  # noqa: BLE001 - publisher failure must not affect caller
            log.warning("servicebus_publish_failed", err=str(exc))


class NullAlertPublisher:
    """Used in tests / when Service Bus is unconfigured."""

    def __init__(self) -> None:
        self.alerts: list[dict[str, Any]] = []
        self._healthy = True

    @property
    def healthy(self) -> bool:
        return self._healthy

    def fail(self) -> None:
        self._healthy = False

    async def publish(self, payload: dict[str, Any]) -> None:
        if not self._healthy:
            log.warning("servicebus_publish_failed_simulated")
            return
        self.alerts.append(payload)

    async def close(self) -> None:
        return None
