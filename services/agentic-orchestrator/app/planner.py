"""State-graph planner inspired by LangGraph but implemented on Semantic Kernel.

The workflow is modelled as a DAG with conditional edges. The planner does NOT
hard-code the agent sequence — at every step it consults:

1. The most recent agent's ``next_agent`` handoff (autonomy via direct routing)
2. The current state (have all required artefacts been produced?)
3. The ReflectorAgent's verdict (reflection-based replanning)

Mermaid diagram of the canonical transitions::

    flowchart TD
      START([alert]) --> TRIAGE[TriageAgent]
      TRIAGE -->|fraud_ring/ato| GRAPH[GraphAnalystAgent]
      TRIAGE -->|cp_fraud| POLICY[PolicyAgent]
      TRIAGE -->|false_positive| POLICY
      TRIAGE -->|dispute| NAR[NarrativeAgent]
      GRAPH --> POLICY
      POLICY --> NAR
      NAR --> CASE[CaseManagerAgent]
      CASE --> REFLECT[ReflectorAgent]
      REFLECT -->|accept| END([done])
      REFLECT -->|replan| GRAPH
      REFLECT -->|replan| POLICY
      REFLECT -->|replan| NAR
      REFLECT -->|escalate| END
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

try:
    from semantic_kernel import Kernel  # type: ignore

    _SK_AVAILABLE = True
except Exception:  # pragma: no cover
    Kernel = None  # type: ignore
    _SK_AVAILABLE = False

from .agents import Agent
from .agents.case_manager import CaseManagerAgent
from .agents.reflector import ReflectorAgent
from .agents.triage import TriageAgent
from .state import AgentResult, ReflectionVerdict, WorkflowState
from .telemetry import logger


# Conditional edges keyed by (current_agent, condition) -> next_agent
EDGES: dict[str, dict[str, str]] = {
    "TriageAgent": {
        "suspected_fraud_ring": "GraphAnalystAgent",
        "account_takeover": "GraphAnalystAgent",
        "card_present_fraud": "PolicyAgent",
        "false_positive_candidate": "PolicyAgent",
        "dispute": "NarrativeAgent",
        "unknown": "NarrativeAgent",
    },
    "GraphAnalystAgent": {"*": "PolicyAgent"},
    "PolicyAgent": {"*": "NarrativeAgent"},
    "NarrativeAgent": {"*": "CaseManagerAgent"},
    "CaseManagerAgent": {"*": "ReflectorAgent"},
    "ReflectorAgent": {
        ReflectionVerdict.ACCEPT.value: "__END__",
        ReflectionVerdict.ESCALATE.value: "__END__",
        # replan target is decided by reflector itself (via next_agent handoff)
    },
}


class Planner:
    """Autonomous planner that drives the multi-agent DAG."""

    MAX_STEPS = 20

    def __init__(self, agents: dict[str, Agent], kernel: Any | None = None) -> None:
        self.agents = agents
        self.kernel = kernel
        if not isinstance(agents.get("TriageAgent"), TriageAgent):
            raise ValueError("Planner requires a TriageAgent")
        if not isinstance(agents.get("ReflectorAgent"), ReflectorAgent):
            raise ValueError("Planner requires a ReflectorAgent")

    # ---------- planning logic ----------

    def decide_next(self, state: WorkflowState, last: AgentResult | None) -> str | None:
        """Decide the next agent based on handoff, edges, and reflection."""

        # 1. Explicit handoff from the last agent always wins
        if last and last.next_agent:
            return last.next_agent

        # 2. Reflector verdict can terminate
        if state.reflection_verdict in (ReflectionVerdict.ACCEPT, ReflectionVerdict.ESCALATE):
            return None

        # 3. Look up conditional edge
        if not state.visited:
            return "TriageAgent"
        current = state.visited[-1]
        edges = EDGES.get(current, {})
        if current == "TriageAgent":
            return edges.get(state.classification.value) or edges.get("unknown")
        if current == "ReflectorAgent" and state.reflection_verdict:
            return edges.get(state.reflection_verdict.value)
        return edges.get("*")

    # ---------- execution ----------

    async def run(self, state: WorkflowState) -> WorkflowState:
        last: AgentResult | None = None
        steps = 0
        while not state.done and steps < self.MAX_STEPS:
            next_name = self.decide_next(state, last)
            if not next_name or next_name == "__END__":
                state.done = True
                break
            agent = self.agents.get(next_name)
            if agent is None:
                logger.warning("unknown_agent", name=next_name)
                state.done = True
                break
            logger.info("planner_step", step=steps, agent=next_name, case_id=state.case_id)
            last = await agent.run(state)
            steps += 1
            # Always persist after each non-persistence step (CaseManager handles its own).
            if not isinstance(agent, (CaseManagerAgent, ReflectorAgent)) and "cases" in agent.deps:
                pass  # case manager will run later via the DAG
        # Ensure the final case is persisted, even if reflector ended things first.
        cm = self.agents.get("CaseManagerAgent")
        if cm and "cases" in cm.deps:
            try:
                await cm.deps["cases"].upsert(state.to_case())
            except Exception as exc:  # pragma: no cover
                logger.warning("final_persist_failed", error=str(exc))
        return state

    async def stream(self, state: WorkflowState) -> AsyncIterator[dict[str, Any]]:
        """Async generator yielding step events — used by the WS endpoint."""

        last: AgentResult | None = None
        steps = 0
        yield {"event": "start", "case_id": state.case_id}
        while not state.done and steps < self.MAX_STEPS:
            next_name = self.decide_next(state, last)
            if not next_name or next_name == "__END__":
                state.done = True
                break
            agent = self.agents.get(next_name)
            if agent is None:
                state.done = True
                break
            yield {"event": "agent_start", "agent": next_name, "step": steps}
            last = await agent.run(state)
            yield {
                "event": "agent_end",
                "agent": next_name,
                "step": steps,
                "summary": last.summary,
                "next_agent": last.next_agent,
                "reason": last.reason,
            }
            steps += 1
            await asyncio.sleep(0)  # cooperative yield
        yield {"event": "end", "case_id": state.case_id, "done": state.done}


def build_kernel() -> Any | None:
    """Construct a Semantic Kernel Kernel if SK is installed."""

    if not _SK_AVAILABLE:
        return None
    try:
        return Kernel()
    except Exception:  # pragma: no cover
        return None
