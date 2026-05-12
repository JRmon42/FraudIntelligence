"""Cosmos DB async point-read client with feature lookups."""

from __future__ import annotations

from typing import Any, Protocol

import structlog
from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential

from .models import CardFeatures, MerchantFeatures
from .settings import Settings

log = structlog.get_logger(__name__)


class FeatureSource(Protocol):
    """Abstract feature source so tests can substitute an in-memory fake."""

    async def get_card(self, card_id: str) -> CardFeatures | None: ...
    async def get_merchant(self, merchant_id: str) -> MerchantFeatures | None: ...
    async def close(self) -> None: ...
    async def ping(self) -> bool: ...


class CosmosFeatureClient:
    """Real Cosmos DB client wrapping point reads on cards / merchants containers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: CosmosClient | None = None
        self._cards: ContainerProxy | None = None
        self._merchants: ContainerProxy | None = None
        self._credential: DefaultAzureCredential | None = None

    async def connect(self) -> None:
        """Pre-warm the Cosmos connection (called at startup)."""

        if self._client is not None:
            return
        if not self._settings.cosmos_endpoint:
            log.warning("cosmos_endpoint_unset", note="feature lookups will return None")
            return

        if self._settings.cosmos_key:
            self._client = CosmosClient(
                self._settings.cosmos_endpoint, credential=self._settings.cosmos_key
            )
        else:
            self._credential = DefaultAzureCredential()
            self._client = CosmosClient(self._settings.cosmos_endpoint, credential=self._credential)

        db = self._client.get_database_client(self._settings.cosmos_database)
        self._cards = db.get_container_client(self._settings.cosmos_cards_container)
        self._merchants = db.get_container_client(self._settings.cosmos_merchants_container)
        log.info("cosmos_connected", endpoint=self._settings.cosmos_endpoint)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._credential is not None:
            await self._credential.close()
            self._credential = None

    async def ping(self) -> bool:
        return self._client is not None

    async def _read(self, container: ContainerProxy | None, item_id: str) -> dict[str, Any] | None:
        if container is None:
            return None
        try:
            return await container.read_item(item=item_id, partition_key=item_id)
        except CosmosResourceNotFoundError:
            return None
        except Exception as exc:  # noqa: BLE001 - upstream failures must not crash hot path
            log.warning("cosmos_read_failed", item_id=item_id, err=str(exc))
            return None

    async def get_card(self, card_id: str) -> CardFeatures | None:
        doc = await self._read(self._cards, card_id)
        if doc is None:
            return None
        return CardFeatures(**{k: v for k, v in doc.items() if not k.startswith("_")})

    async def get_merchant(self, merchant_id: str) -> MerchantFeatures | None:
        doc = await self._read(self._merchants, merchant_id)
        if doc is None:
            return None
        return MerchantFeatures(**{k: v for k, v in doc.items() if not k.startswith("_")})


class InMemoryFeatureClient:
    """Tiny in-memory fake used by tests and local dev when Cosmos is unset."""

    def __init__(
        self,
        cards: dict[str, CardFeatures] | None = None,
        merchants: dict[str, MerchantFeatures] | None = None,
    ) -> None:
        self._cards = cards or {}
        self._merchants = merchants or {}

    async def get_card(self, card_id: str) -> CardFeatures | None:
        return self._cards.get(card_id)

    async def get_merchant(self, merchant_id: str) -> MerchantFeatures | None:
        return self._merchants.get(merchant_id)

    async def close(self) -> None:
        return None

    async def ping(self) -> bool:
        return True
