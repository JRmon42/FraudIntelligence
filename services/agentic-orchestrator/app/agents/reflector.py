"""ReflectorAgent — reviews the case after each step and may request replanning.

This implements the *reflection* loop in the Reflexion / Plan-and-Reflect
pattern. The reflector inspects the workflow state, decides whether the case
is complete, missing artefacts, or requires escalation, and returns a verdict
that the planner uses to decide whether to halt or to inject another agent
into the plan.
"""

from __future__ import annotations

import json

from ..llm import LLMMessage
from ..state import AgentResult, ReflectionVerdict, WorkflowState
from .base import Agent

SYS = (
    "AGENT: ReflectorAgent. You are a critical reviewer. Given the case state "
    "verify completeness: there must be a graph analysis (if classification is "
    "suspected_fraud_ring or account_takeover), a policy mapping, and both SAR "
    "and EBA narratives. Return JSON {verdict, reason, missing_steps:[...]}. "
    "verdict ∈ {accept, replan, escalate}."
)


REQUIRED_BY_CLASS: dict[str, set[str]] = {
    "suspected_fraud_ring": {"GraphAnalystAgent", "PolicyAgent", "NarrativeAgent"},
    "account_takeover": {"GraphAnalystAgent", "PolicyAgent", "NarrativeAgent"},
    "card_present_fraud": {"PolicyAgent", "NarrativeAgent"},
    "false_positive_candidate": {"PolicyAgent"},
    "dispute": {"NarrativeAgent"},
    "unknown": set(),
}


class ReflectorAgent(Agent):
    name = "ReflectorAgent"
    description = "Reflects on case completeness and may request another agent pass."
    tools: list[str] = []

    async def _run(self, state: WorkflowState) -> AgentResult:
        # Deterministic gap analysis first — robust even if the LLM is mocked.
        required = REQUIRED_BY_CLASS.get(state.classification.value, set())
        visited = set(state.visited)
        missing = sorted(required - visited)

        # Also flag missing artefacts on the state itself.
        artefact_gaps: list[str] = []
        if "GraphAnalystAgent" in required and state.graph is None:
            artefact_gaps.append("graph")
        if "PolicyAgent" in required and state.policy is None:
            artefact_gaps.append("policy")
        if "NarrativeAgent" in required and not state.narrative_sar:
            artefact_gaps.append("narrative")

        # Ask the LLM for a second opinion (purely additive).
        ctx = {
            "classification": state.classification.value,
            "visited": state.visited,
            "missing_agents": missing,
            "artefact_gaps": artefact_gaps,
            "reflections_used": state.reflections_used,
            "reflection_budget": state.reflection_budget,
        }
        resp = await self.llm.chat(
            [LLMMessage("system", SYS), LLMMessage("user", json.dumps(ctx))],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        parsed = self.parse_json(resp.get("content"))

        if (
            missing or artefact_gaps
        ) and state.reflections_used < state.reflection_budget:
            verdict = ReflectionVerdict.REPLAN
            next_agent = (
                missing[0] if missing else self._agent_for_artefact(artefact_gaps[0])
            )
            reason = f"missing {missing or artefact_gaps}"
            state.reflections_used += 1
        elif missing or artefact_gaps:
            verdict = ReflectionVerdict.ESCALATE
            next_agent = None
            reason = (
                f"reflection budget exhausted; gaps remain: {missing or artefact_gaps}"
            )
            state.done = True
        else:
            # If LLM disagrees and demands replan, honour it within budget.
            llm_verdict = (parsed.get("verdict") or "accept").lower()
            if (
                llm_verdict == "replan"
                and state.reflections_used < state.reflection_budget
            ):
                verdict = ReflectionVerdict.REPLAN
                next_agent = (parsed.get("missing_steps") or ["NarrativeAgent"])[0]
                reason = parsed.get("reason", "LLM requested replan")
                state.reflections_used += 1
            else:
                verdict = ReflectionVerdict.ACCEPT
                next_agent = None
                reason = parsed.get("reason", "all required artefacts present")
                state.done = True

        state.reflection_verdict = verdict
        state.next_agent = next_agent
        return AgentResult(
            agent=self.name,
            summary=f"verdict={verdict.value}; next={next_agent}",
            data={
                "verdict": verdict.value,
                "missing_agents": missing,
                "artefact_gaps": artefact_gaps,
                "reflections_used": state.reflections_used,
            },
            next_agent=next_agent,
            reason=reason,
            done=state.done,
        )

    @staticmethod
    def _agent_for_artefact(artefact: str) -> str:
        return {
            "graph": "GraphAnalystAgent",
            "policy": "PolicyAgent",
            "narrative": "NarrativeAgent",
        }.get(artefact, "NarrativeAgent")
