"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from app.agents import build_default_agents
from app.cosmos import build_cases, build_graph
from app.llm import build_llm
from app.planner import Planner
from app.state import Alert, WorkflowState


@pytest.fixture
def llm():
    return build_llm(mock=True)


@pytest.fixture
def graph():
    return build_graph(mock=True)


@pytest.fixture
def cases():
    return build_cases(mock=True)


@pytest.fixture
def agents(llm, graph, cases):
    return build_default_agents(llm, graph=graph, cases=cases)


@pytest.fixture
def planner(agents):
    return Planner(agents)


@pytest.fixture
def fraud_ring_alert():
    return Alert(
        transaction_id="t1",
        card_id="card-A1",
        merchant_id="merch-9001",
        device_id="device-FP-7731",
        amount=487.55,
        currency="EUR",
        score=0.94,
        reason_codes=["velocity", "shared_device"],
    )


@pytest.fixture
def state(fraud_ring_alert):
    return WorkflowState(alert=fraud_ring_alert, reflection_budget=2)
