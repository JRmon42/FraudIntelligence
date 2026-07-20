"""TriageAgent — classifies incoming alerts and proposes a downstream plan."""

from __future__ import annotations

import json

from ..llm import LLMMessage
from ..state import AgentResult, Classification, WorkflowState
from .base import Agent

CLASSIFY_SYS = (
    "AGENT: TriageAgent. You are a senior fraud triage analyst. "
    "Classify the alert into exactly one of: suspected_fraud_ring, account_takeover, "
    "card_present_fraud, false_positive_candidate, dispute. "
    "Then list which downstream agents should run from this set: "
    "GraphAnalystAgent, PolicyAgent, NarrativeAgent. "
    "Respond as JSON: {classification, rationale, recommended_agents:[...]}."
)


class TriageAgent(Agent):
    name = "TriageAgent"
    description = (
        "Classifies fraud alerts and proposes the initial downstream agent plan."
    )
    tools: list[str] = []

    async def _run(self, state: WorkflowState) -> AgentResult:
        a = state.alert
        user_payload = {
            "alert_id": a.alert_id,
            "amount": a.amount,
            "currency": a.currency,
            "score": a.score,
            "reason_codes": a.reason_codes,
            "card_id": a.card_id,
            "device_id": a.device_id,
            "merchant_id": a.merchant_id,
        }
        resp = await self.llm.chat(
            [
                LLMMessage("system", CLASSIFY_SYS),
                LLMMessage("user", json.dumps(user_payload)),
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        parsed = self.parse_json(resp.get("content"))

        cls_raw = parsed.get("classification") or self._heuristic_classify(state)
        try:
            classification = Classification(cls_raw)
        except ValueError:
            classification = Classification.UNKNOWN
        state.classification = classification

        plan: list[str] = parsed.get("recommended_agents") or self._default_plan(
            classification
        )
        state.next_agent = plan[0] if plan else "ReflectorAgent"

        return AgentResult(
            agent=self.name,
            summary=f"classified={classification.value}; plan={plan}",
            data={
                "classification": classification.value,
                "rationale": parsed.get("rationale", ""),
                "plan": plan,
            },
            next_agent=state.next_agent,
            reason=parsed.get("rationale", "triage classification"),
        )

    @staticmethod
    def _heuristic_classify(state: WorkflowState) -> str:
        codes = {c.lower() for c in state.alert.reason_codes}
        if {"velocity", "shared_device"} & codes:
            return Classification.SUSPECTED_FRAUD_RING.value
        if "ato" in codes or "account_takeover" in codes:
            return Classification.ACCOUNT_TAKEOVER.value
        if state.alert.amount and state.alert.amount > 1000:
            return Classification.CARD_PRESENT_FRAUD.value
        return Classification.FALSE_POSITIVE_CANDIDATE.value

    @staticmethod
    def _default_plan(classification: Classification) -> list[str]:
        if classification == Classification.SUSPECTED_FRAUD_RING:
            return ["GraphAnalystAgent", "PolicyAgent", "NarrativeAgent"]
        if classification == Classification.ACCOUNT_TAKEOVER:
            return ["GraphAnalystAgent", "PolicyAgent", "NarrativeAgent"]
        if classification == Classification.CARD_PRESENT_FRAUD:
            return ["PolicyAgent", "NarrativeAgent"]
        if classification == Classification.FALSE_POSITIVE_CANDIDATE:
            return ["PolicyAgent"]
        return ["NarrativeAgent"]
