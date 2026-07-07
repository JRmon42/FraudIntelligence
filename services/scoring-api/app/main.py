"""FastAPI app factory + lifespan wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from .api import HotPath, router
from .cosmos_client import CosmosFeatureClient, FeatureSource, InMemoryFeatureClient
from .eh_producer import DecisionEmitter, EventHubsDecisionEmitter, NullDecisionEmitter
from .features import AggregatesStore, FeatureLookup
from .scoring import OnnxScorer
from .settings import Settings, get_settings
from .telemetry import configure_logging, configure_tracing

log = structlog.get_logger(__name__)


async def _build_hot_path(settings: Settings) -> tuple[HotPath, list[object]]:
    """Construct shared singletons. Returns (hot_path, closeables)."""

    closeables: list[object] = []

    source: FeatureSource
    if settings.cosmos_endpoint:
        cosmos = CosmosFeatureClient(settings)
        await cosmos.connect()
        source = cosmos
        closeables.append(cosmos)
    elif settings.seed_demo_features:
        from .seed_data import demo_cards, demo_merchants

        cards = demo_cards()
        merchants = demo_merchants()
        log.info(
            "cosmos_disabled_using_seeded_inmemory",
            cards=len(cards),
            merchants=len(merchants),
        )
        source = InMemoryFeatureClient(cards=cards, merchants=merchants)
    else:
        log.info("cosmos_disabled_using_inmemory")
        source = InMemoryFeatureClient()

    features = FeatureLookup(source, settings)
    aggregates = await AggregatesStore.create(settings)
    closeables.append(aggregates)
    if settings.redis_seed_aggregates:
        try:
            await aggregates.seed_demo()
        except Exception as exc:  # noqa: BLE001
            log.warning("aggregates_seed_skipped", err=str(exc))

    emitter: DecisionEmitter
    if settings.eventhub_fqdn or settings.eventhub_conn_str:
        eh = EventHubsDecisionEmitter(settings)
        await eh.connect()
        emitter = eh
        closeables.append(eh)
    else:
        emitter = NullDecisionEmitter()

    scorer = OnnxScorer(settings.model_path, settings.model_version)
    return (
        HotPath(features=features, aggregates=aggregates, scorer=scorer, emitter=emitter),
        closeables,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    hot, closeables = await _build_hot_path(settings)
    app.state.hot = hot
    app.state.closeables = closeables
    log.info(
        "scoring_api_ready",
        model_version=hot.scorer.model_version,
        port=settings.scoring_api_port,
    )
    try:
        yield
    finally:
        for c in closeables:
            close = getattr(c, "close", None)
            if close is not None:
                try:
                    await close()
                except Exception:  # noqa: BLE001, S110
                    pass


def create_app(settings: Settings | None = None, hot: HotPath | None = None) -> FastAPI:
    """Build a FastAPI instance. ``hot`` lets tests inject in-memory deps."""

    settings = settings or get_settings()
    configure_logging(settings)
    configure_tracing(settings)

    if hot is not None:
        # Pre-built deps for tests: skip lifespan construction.
        app = FastAPI(
            title="Heimdall Scoring API",
            version="0.1.0",
            default_response_class=_orjson_response(),
        )
        app.state.settings = settings
        app.state.hot = hot
        app.state.closeables = []
    else:
        app = FastAPI(
            title="Heimdall Scoring API",
            version="0.1.0",
            lifespan=lifespan,
            default_response_class=_orjson_response(),
        )
        app.state.settings = settings

    app.include_router(router)

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz")
    except Exception:  # noqa: BLE001
        log.warning("otel_fastapi_instrumentation_failed")

    return app


def _orjson_response() -> type:
    from fastapi.responses import ORJSONResponse

    return ORJSONResponse


app = create_app()
