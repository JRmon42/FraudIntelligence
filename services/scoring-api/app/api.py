"""HTTP API surface and per-stage scoring orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass

import structlog
from fastapi import APIRouter, HTTPException, Query, Request

from .eh_producer import DecisionEmitter
from .features import AggregatesStore, FeatureLookup
from .models import ScoreRequest, ScoreResponse, StageTimings
from .psd2_optimizer import (
    ExemptionContext,
    build_reason_codes,
    decide,
    select_exemption,
)
from .scoring import OnnxScorer, ScoringContext
from .telemetry import get_tracer

log = structlog.get_logger(__name__)
router = APIRouter()


@dataclass
class HotPath:
    """Bundle of singletons injected via app.state."""

    features: FeatureLookup
    aggregates: AggregatesStore
    scorer: OnnxScorer
    emitter: DecisionEmitter


def _hot(request: Request) -> HotPath:
    return request.app.state.hot  # type: ignore[no-any-return]


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict[str, object]:
    hot = _hot(request)
    cosmos_ok = await hot.features._source.ping()  # type: ignore[attr-defined]
    redis_ok = await hot.aggregates.ping()
    ready = cosmos_ok and redis_ok
    return {
        "ready": ready,
        "cosmos": cosmos_ok,
        "redis": redis_ok,
        "model_loaded": hot.scorer.loaded,
        "eventhub": hot.emitter.healthy,
    }


@router.post("/v1/score", response_model=ScoreResponse, response_model_exclude_none=True)
async def score(
    payload: ScoreRequest,
    request: Request,
    explain: bool = Query(default=False),
) -> ScoreResponse:
    hot = _hot(request)
    tracer = get_tracer()
    t0 = time.perf_counter()

    try:
        with tracer.start_as_current_span("score.features"):
            ts = time.perf_counter()
            card = await hot.features.get_card(payload.card_id)
            merchant = await hot.features.get_merchant(payload.merchant_id)
            features_ms = (time.perf_counter() - ts) * 1000.0

        with tracer.start_as_current_span("score.aggregates"):
            ts = time.perf_counter()
            aggregates = await hot.aggregates.get_for_card(payload.card_id)
            aggregates_ms = (time.perf_counter() - ts) * 1000.0

        with tracer.start_as_current_span("score.inference"):
            ts = time.perf_counter()
            ctx = ScoringContext(
                request=payload, card=card, merchant=merchant, aggregates=aggregates
            )
            score_value = hot.scorer.score(ctx)
            inference_ms = (time.perf_counter() - ts) * 1000.0

        with tracer.start_as_current_span("score.psd2"):
            ts = time.perf_counter()
            ex_ctx = ExemptionContext(
                request=payload,
                card=card,
                merchant=merchant,
                cumulative_amount_eur=aggregates.amount_1h,
                cumulative_count=aggregates.count_1h,
                score=score_value,
            )
            exemption = select_exemption(ex_ctx)
            decision = decide(score_value, exemption, card)
            reason_codes = build_reason_codes(score_value, exemption, ex_ctx)
            psd2_ms = (time.perf_counter() - ts) * 1000.0

        with tracer.start_as_current_span("score.emit"):
            ts = time.perf_counter()
            await hot.emitter.emit(
                {
                    "transaction_id": payload.transaction_id,
                    "card_id": payload.card_id,
                    "merchant_id": payload.merchant_id,
                    "decision": decision,
                    "score": score_value,
                    "psd2_exemption": exemption,
                    "model_version": hot.scorer.model_version,
                    "ts": payload.timestamp.isoformat(),
                }
            )
            emit_ms = (time.perf_counter() - ts) * 1000.0
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("score_failed", err=str(exc), txn_id=payload.transaction_id)
        raise HTTPException(status_code=500, detail="scoring_failed") from exc

    latency_ms = (time.perf_counter() - t0) * 1000.0
    timings = (
        StageTimings(
            features_ms=round(features_ms, 3),
            aggregates_ms=round(aggregates_ms, 3),
            inference_ms=round(inference_ms, 3),
            psd2_ms=round(psd2_ms, 3),
            emit_ms=round(emit_ms, 3),
        )
        if explain
        else None
    )

    log.info(
        "scored",
        txn_id=payload.transaction_id,
        decision=decision,
        score=round(score_value, 4),
        psd2=exemption,
        latency_ms=round(latency_ms, 3),
    )

    return ScoreResponse(
        decision=decision,  # type: ignore[arg-type]
        score=score_value,
        reason_codes=reason_codes,
        psd2_exemption=exemption,
        model_version=hot.scorer.model_version,
        latency_ms=round(latency_ms, 3),
        explain=timings,
    )
