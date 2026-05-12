"""Feature lookup with an async TTL+LRU cache for hot cards."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Generic, TypeVar

import structlog

from .cosmos_client import FeatureSource
from .models import Aggregates, CardFeatures, MerchantFeatures
from .settings import Settings

log = structlog.get_logger(__name__)
T = TypeVar("T")


class AsyncTTLCache(Generic[T]):
    """Bounded async LRU cache with per-entry TTL."""

    def __init__(self, max_size: int, ttl_s: float) -> None:
        self._max = max_size
        self._ttl = ttl_s
        self._data: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T | None:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            ts, val = entry
            if time.monotonic() - ts > self._ttl:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return val

    async def set(self, key: str, value: T) -> None:
        async with self._lock:
            self._data[key] = (time.monotonic(), value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


class FeatureLookup:
    """Combines Cosmos point reads with a small hot-card cache."""

    def __init__(self, source: FeatureSource, settings: Settings) -> None:
        self._source = source
        self._card_cache: AsyncTTLCache[CardFeatures] = AsyncTTLCache(
            settings.card_cache_size, settings.card_cache_ttl_s
        )
        self._merchant_cache: AsyncTTLCache[MerchantFeatures] = AsyncTTLCache(
            settings.card_cache_size, settings.card_cache_ttl_s
        )

    async def get_card(self, card_id: str) -> CardFeatures | None:
        cached = await self._card_cache.get(card_id)
        if cached is not None:
            return cached
        card = await self._source.get_card(card_id)
        if card is not None:
            await self._card_cache.set(card_id, card)
        return card

    async def get_merchant(self, merchant_id: str) -> MerchantFeatures | None:
        cached = await self._merchant_cache.get(merchant_id)
        if cached is not None:
            return cached
        merchant = await self._source.get_merchant(merchant_id)
        if merchant is not None:
            await self._merchant_cache.set(merchant_id, merchant)
        return merchant


class AggregatesStore:
    """Real-time aggregates pulled from a Redis-compatible store.

    Production: Azure Cache for Redis (or Cosmos w/ Redis API). Tests:
    `fakeredis.aioredis.FakeRedis`. Both expose the same `redis.asyncio` interface.
    """

    def __init__(self, client: object) -> None:
        self._r = client

    @classmethod
    async def create(cls, settings: Settings) -> AggregatesStore:
        client: object
        if settings.redis_fake or settings.scoring_api_env == "test":
            try:
                import fakeredis.aioredis as fakeredis_aio

                client = fakeredis_aio.FakeRedis(decode_responses=True)
            except ImportError:  # pragma: no cover - fallback if fakeredis missing in prod image
                from redis.asyncio import Redis

                client = Redis.from_url(settings.redis_url, decode_responses=True)
        else:
            from redis.asyncio import Redis

            client = Redis.from_url(settings.redis_url, decode_responses=True)
        return cls(client)

    async def close(self) -> None:
        close = getattr(self._r, "aclose", None) or getattr(self._r, "close", None)
        if close is not None:
            res = close()
            if asyncio.iscoroutine(res):
                await res

    async def ping(self) -> bool:
        try:
            return bool(await self._r.ping())  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            return False

    async def get_for_card(self, card_id: str) -> Aggregates:
        key = f"agg:card:{card_id}"
        try:
            data = await self._r.hgetall(key)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            log.warning("aggregates_read_failed", card_id=card_id, err=str(exc))
            return Aggregates()
        if not data:
            return Aggregates()
        return Aggregates(
            amount_1h=float(data.get("amount_1h", 0.0)),
            count_1h=int(data.get("count_1h", 0)),
            declined_1h=int(data.get("declined_1h", 0)),
        )

    async def bump(
        self, card_id: str, amount: float, declined: bool = False, ttl_s: int = 3600
    ) -> None:
        """Helper used by tests/local: increment the rolling aggregates."""

        key = f"agg:card:{card_id}"
        pipe = self._r.pipeline()  # type: ignore[union-attr]
        pipe.hincrbyfloat(key, "amount_1h", amount)
        pipe.hincrby(key, "count_1h", 1)
        if declined:
            pipe.hincrby(key, "declined_1h", 1)
        pipe.expire(key, ttl_s)
        await pipe.execute()
