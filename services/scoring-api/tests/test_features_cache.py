"""Tests for the AsyncTTLCache + FeatureLookup hot-card cache."""

from __future__ import annotations

import asyncio

import pytest

from app.cosmos_client import InMemoryFeatureClient
from app.features import AsyncTTLCache, FeatureLookup
from app.models import CardFeatures
from app.settings import Settings


@pytest.mark.asyncio
async def test_ttl_cache_returns_value_within_ttl() -> None:
    cache: AsyncTTLCache[str] = AsyncTTLCache(max_size=10, ttl_s=5.0)
    await cache.set("k", "v")
    assert await cache.get("k") == "v"


@pytest.mark.asyncio
async def test_ttl_cache_expires() -> None:
    cache: AsyncTTLCache[str] = AsyncTTLCache(max_size=10, ttl_s=0.05)
    await cache.set("k", "v")
    await asyncio.sleep(0.07)
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_ttl_cache_evicts_lru() -> None:
    cache: AsyncTTLCache[int] = AsyncTTLCache(max_size=2, ttl_s=10.0)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)
    assert await cache.get("a") is None
    assert await cache.get("b") == 2
    assert await cache.get("c") == 3


@pytest.mark.asyncio
async def test_feature_lookup_caches_card() -> None:
    settings = Settings(card_cache_size=10, card_cache_ttl_s=10.0)
    cards = {"card_x": CardFeatures(card_id="card_x", risk_tier=1)}
    src = InMemoryFeatureClient(cards=cards)
    lookup = FeatureLookup(src, settings)

    first = await lookup.get_card("card_x")
    # Mutate underlying source; cache must keep returning the cached value.
    cards["card_x"] = CardFeatures(card_id="card_x", risk_tier=5)
    second = await lookup.get_card("card_x")
    assert first is not None and second is not None
    assert first.risk_tier == second.risk_tier == 1
