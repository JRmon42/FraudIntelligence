from __future__ import annotations

import pytest

from app.agents import build_default_agents
from app.cosmos import build_cases, build_graph
from app.llm import build_llm
from app.planner import EDGES, Planner
from app.state import AgentResult, Alert, Classification, ReflectionVerdict, WorkflowState


def test_edges_cover_all_classifications():
    triage_edges = EDGES["TriageAgent"]
    for cls in Classification:
        assert cls.value in triage_edges, f"missing edge for {cls}"


def test_decide_next_starts_with_triage(planner, state):
    assert planner.decide_next(state, None) == "TriageAgent"


def test_decide_next_honours_handoff(planner, state):
    state.visited.append("TriageAgent")
    state.classification = Classification.SUSPECTED_FRAUD_RING
    last = AgentResult(agent="TriageAgent", summary="x", next_agent="GraphAnalystAgent")
    assert planner.decide_next(state, last) == "GraphAnalystAgent"


def test_decide_next_uses_classification_edge(planner, state):
    state.visited.append("TriageAgent")
    state.classification = Classification.CARD_PRESENT_FRAUD
    assert planner.decide_next(state, None) == "PolicyAgent"


def test_reflector_accept_terminates(planner, state):
    state.visited.append("ReflectorAgent")
    state.reflection_verdict = ReflectionVerdict.ACCEPT
    assert planner.decide_next(state, None) is None


def test_planner_requires_triage_and_reflector():
    llm = build_llm(mock=True)
    graph = build_graph(mock=True)
    cases = build_cases(mock=True)
    agents = build_default_agents(llm, graph=graph, cases=cases)
    del agents["TriageAgent"]
    with pytest.raises(ValueError):
        Planner(agents)
