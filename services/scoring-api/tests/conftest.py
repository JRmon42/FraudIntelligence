"""Shared pytest fixtures for the scoring-api test suite."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Force test-mode env BEFORE importing app modules.
os.environ.setdefault("SCORING_API_ENV", "test")
os.environ.setdefault("REDIS_FAKE", "1")
os.environ.setdefault("COSMOS_ENDPOINT", "")
os.environ.setdefault("EVENTHUB_FQDN", "")
os.environ.setdefault("EVENTHUB_CONN_STR", "")
os.environ.setdefault("MODEL_PATH", "/nonexistent/model.onnx")
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")

from app.api import HotPath  # noqa: E402
from app.cosmos_client import InMemoryFeatureClient  # noqa: E402
from app.eh_producer import NullDecisionEmitter  # noqa: E402
from app.features import AggregatesStore, FeatureLookup  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import CardFeatures, MerchantFeatures  # noqa: E402
from app.sb_producer import NullAlertPublisher  # noqa: E402
from app.scoring import OnnxScorer  # noqa: E402
from app.settings import get_settings  # noqa: E402


@pytest.fixture
def cards() -> dict[str, CardFeatures]:
    return {
        "card_ok": CardFeatures(
            card_id="card_ok", risk_tier=1, issue_country="SE", customer_segment="retail"
        ),
        "card_blocked": CardFeatures(card_id="card_blocked", risk_tier=5, is_blocked=True),
        "card_corp": CardFeatures(
            card_id="card_corp", risk_tier=0, customer_segment="corporate", issue_country="SE"
        ),
        "card_trusted": CardFeatures(
            card_id="card_trusted", risk_tier=0, customer_segment="trusted", issue_country="SE"
        ),
        "card_risky": CardFeatures(
            card_id="card_risky", risk_tier=4, chargebacks_30d=3, issue_country="SE"
        ),
    }


@pytest.fixture
def merchants() -> dict[str, MerchantFeatures]:
    return {
        "mrc_safe": MerchantFeatures(
            merchant_id="mrc_safe", country="SE", risk_score=0.05, fraud_rate_30d=0.00005
        ),
        "mrc_tra_eligible": MerchantFeatures(
            merchant_id="mrc_tra_eligible", country="SE", risk_score=0.1, fraud_rate_30d=0.0005
        ),
        "mrc_high_risk": MerchantFeatures(
            merchant_id="mrc_high_risk",
            country="SE",
            risk_score=0.9,
            fraud_rate_30d=0.04,
            high_risk=True,
        ),
    }


@pytest_asyncio.fixture
async def hot(
    cards: dict[str, CardFeatures], merchants: dict[str, MerchantFeatures]
) -> AsyncIterator[HotPath]:
    settings = get_settings()
    source = InMemoryFeatureClient(cards=cards, merchants=merchants)
    features = FeatureLookup(source, settings)
    aggregates = await AggregatesStore.create(settings)
    emitter = NullDecisionEmitter()
    alerts = NullAlertPublisher()
    scorer = OnnxScorer(settings.model_path, settings.model_version)
    yield HotPath(
        features=features,
        aggregates=aggregates,
        scorer=scorer,
        emitter=emitter,
        alerts=alerts,
    )
    await aggregates.close()


@pytest_asyncio.fixture
async def client(hot: HotPath) -> AsyncIterator[AsyncClient]:
    app = create_app(hot=hot)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
