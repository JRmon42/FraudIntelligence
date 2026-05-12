"""End-to-end /v1/score behaviour."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

from .factories import make_payload


@pytest.mark.asyncio
async def test_score_happy_path_approve(client: AsyncClient) -> None:
    r = await client.post("/v1/score", json=make_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "APPROVE"
    assert 0.0 <= body["score"] <= 1.0
    assert body["psd2_exemption"] in {"TRA", "LOW_VALUE", "NONE"}
    assert "model_version" in body
    assert body["latency_ms"] >= 0.0


@pytest.mark.asyncio
async def test_score_blocked_card_declined(client: AsyncClient) -> None:
    payload = make_payload(card_id="card_blocked", transaction_id="txn_blk")
    r = await client.post("/v1/score", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "DECLINE"
    assert "CARD_BLOCKED" in body["reason_codes"]


@pytest.mark.asyncio
async def test_score_high_risk_merchant_triggers_sca(client: AsyncClient) -> None:
    payload = make_payload(
        card_id="card_risky",
        merchant_id="mrc_high_risk",
        amount=750.0,
        transaction_id="txn_hr",
    )
    r = await client.post("/v1/score", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] in {"SCA", "DECLINE"}
    assert "MERCHANT_HIGH_RISK" in body["reason_codes"]


@pytest.mark.asyncio
async def test_score_missing_card_does_not_crash(client: AsyncClient) -> None:
    payload = make_payload(card_id="card_unknown_999", transaction_id="txn_miss")
    r = await client.post("/v1/score", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] in {"APPROVE", "SCA", "DECLINE"}


@pytest.mark.asyncio
async def test_score_explain_returns_stage_timings(client: AsyncClient) -> None:
    r = await client.post("/v1/score?explain=true", json=make_payload(transaction_id="txn_exp"))
    assert r.status_code == 200
    body = r.json()
    assert body["explain"] is not None
    for k in ("features_ms", "aggregates_ms", "inference_ms", "psd2_ms", "emit_ms"):
        assert k in body["explain"]
        assert body["explain"][k] >= 0.0


@pytest.mark.asyncio
async def test_score_validation_rejects_bad_currency(client: AsyncClient) -> None:
    r = await client.post("/v1/score", json=make_payload(currency="EURO"))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_score_latency_under_50ms(client: AsyncClient) -> None:
    # Warm the cache.
    await client.post("/v1/score", json=make_payload(transaction_id="warm"))
    t0 = time.perf_counter()
    r = await client.post("/v1/score", json=make_payload(transaction_id="hot"))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert r.status_code == 200
    # In-process ASGI client should comfortably meet < 50 ms.
    assert elapsed_ms < 50.0, f"latency {elapsed_ms:.2f} ms exceeds 50 ms budget"


@pytest.mark.asyncio
async def test_score_decision_event_emitted(client: AsyncClient, hot) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/v1/score", json=make_payload(transaction_id="txn_emit"))
    assert r.status_code == 200
    # NullDecisionEmitter records the payload.
    assert any(e["transaction_id"] == "txn_emit" for e in hot.emitter.events)


@pytest.mark.asyncio
async def test_score_eventhub_failure_does_not_break_response(client: AsyncClient, hot) -> None:  # type: ignore[no-untyped-def]
    hot.emitter.fail()
    r = await client.post("/v1/score", json=make_payload(transaction_id="txn_eh_fail"))
    assert r.status_code == 200
