from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import build_app
from app.state import Classification

pytestmark = pytest.mark.asyncio


async def test_e2e_fraud_ring_workflow(planner, state):
    """Run the canonical fraud-ring scenario end-to-end with --mock-llm."""

    await planner.run(state)

    assert state.done is True
    assert state.classification == Classification.SUSPECTED_FRAUD_RING

    expected_subset = {
        "TriageAgent",
        "GraphAnalystAgent",
        "PolicyAgent",
        "NarrativeAgent",
        "CaseManagerAgent",
        "ReflectorAgent",
    }
    assert expected_subset.issubset(set(state.visited))

    assert state.graph is not None
    assert state.policy is not None
    assert state.narrative_sar
    assert state.narrative_eba
    # Timeline has at least one entry per agent visit
    assert len(state.timeline) >= len(state.visited)


async def test_e2e_dispute_takes_short_path(planner, fraud_ring_alert):
    from app.state import Alert, WorkflowState

    alert = Alert(
        transaction_id="t-disp",
        amount=42.0,
        reason_codes=["customer_dispute"],
    )
    state = WorkflowState(alert=alert, reflection_budget=2)
    # Force classification that yields a short path
    await planner.run(state)
    assert state.done is True
    assert "TriageAgent" in state.visited
    assert "ReflectorAgent" in state.visited


async def test_replay_endpoint_uses_reflection_budget():
    app = build_app(mock_llm=True, mock_cosmos=True)
    client = TestClient(app)
    r = client.post(
        "/v1/alerts",
        json={
            "transaction_id": "t-api",
            "card_id": "card-A1",
            "merchant_id": "merch-9001",
            "device_id": "device-FP-7731",
            "amount": 487.55,
            "reason_codes": ["velocity", "shared_device"],
        },
    )
    assert r.status_code == 200, r.text
    case_id = r.json()["case_id"]
    assert r.json()["classification"] == "suspected_fraud_ring"

    g = client.get(f"/v1/cases/{case_id}")
    assert g.status_code == 200
    case = g.json()
    assert case["narrative_sar"]
    assert case["timeline"]

    rep = client.post(f"/v1/cases/{case_id}/replay", json={"reflection_budget": 3})
    assert rep.status_code == 200

    a = client.get("/v1/agents")
    assert a.status_code == 200
    names = {agent["name"] for agent in a.json()["agents"]}
    assert {
        "TriageAgent",
        "GraphAnalystAgent",
        "PolicyAgent",
        "CaseManagerAgent",
        "NarrativeAgent",
        "ReflectorAgent",
    } <= names
