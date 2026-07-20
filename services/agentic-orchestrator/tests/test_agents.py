from __future__ import annotations

import pytest

from app.agents.graph_analyst import GraphAnalystAgent
from app.agents.narrative import NarrativeAgent
from app.agents.policy import PolicyAgent
from app.agents.reflector import ReflectorAgent
from app.agents.triage import TriageAgent
from app.state import Classification, ReflectionVerdict, WorkflowState

pytestmark = pytest.mark.asyncio


async def test_triage_classifies_fraud_ring(llm, state):
    agent = TriageAgent(llm)
    result = await agent.run(state)
    assert state.classification == Classification.SUSPECTED_FRAUD_RING
    assert result.next_agent in {"GraphAnalystAgent", "PolicyAgent", "NarrativeAgent"}
    assert "classification" in result.data


async def test_graph_analyst_pulls_neighbourhood(llm, graph, state):
    state.classification = Classification.SUSPECTED_FRAUD_RING
    agent = GraphAnalystAgent(llm, graph=graph)
    result = await agent.run(state)
    assert state.graph is not None
    assert state.graph.anomaly_score > 0
    assert result.next_agent == "PolicyAgent"


async def test_policy_agent_produces_findings(llm, graph, state):
    state.classification = Classification.SUSPECTED_FRAUD_RING
    await GraphAnalystAgent(llm, graph=graph).run(state)
    result = await PolicyAgent(llm).run(state)
    assert state.policy is not None
    assert state.policy.eba_categories
    assert result.next_agent == "NarrativeAgent"


async def test_narrative_agent_drafts_sar(llm, graph, state):
    state.classification = Classification.SUSPECTED_FRAUD_RING
    await GraphAnalystAgent(llm, graph=graph).run(state)
    await PolicyAgent(llm).run(state)
    await NarrativeAgent(llm).run(state)
    assert state.narrative_sar
    assert state.narrative_eba
    assert "Suspicious Activity Report" in state.narrative_sar


async def test_reflector_replans_when_artefacts_missing(llm, fraud_ring_alert):
    s = WorkflowState(alert=fraud_ring_alert, reflection_budget=2)
    s.classification = Classification.SUSPECTED_FRAUD_RING
    s.visited.append("CaseManagerAgent")
    result = await ReflectorAgent(llm).run(s)
    assert result.data["verdict"] == ReflectionVerdict.REPLAN.value
    assert s.reflections_used == 1
    assert s.next_agent in {"GraphAnalystAgent", "PolicyAgent", "NarrativeAgent"}


async def test_reflector_accepts_when_complete(llm, graph, state):
    state.classification = Classification.SUSPECTED_FRAUD_RING
    await GraphAnalystAgent(llm, graph=graph).run(state)
    await PolicyAgent(llm).run(state)
    await NarrativeAgent(llm).run(state)
    result = await ReflectorAgent(llm).run(state)
    assert result.data["verdict"] == ReflectionVerdict.ACCEPT.value
    assert state.done is True
