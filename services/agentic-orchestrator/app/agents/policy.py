"""PolicyAgent — maps findings to PSD2 SCA exemptions and EBA categories.

Uses the LLM with tool-calling for nuanced rationale, but falls back to a
deterministic rule engine so it works fully offline.
"""

from __future__ import annotations

import json

from ..llm import LLMMessage
from ..state import AgentResult, Classification, PolicyFindings, WorkflowState
from ..tools import evaluate_sca_exemptions
from .base import Agent

SYS = (
    "AGENT: PolicyAgent. You are a PSD2 / EBA compliance specialist. "
    "Given the alert, graph context and the deterministic SCA evaluation, "
    "produce JSON {sca_exemptions_applied:[], sca_exemptions_blocked:[], "
    "eba_categories:[], rationale:''} mapping findings to PSD2 RTS articles "
    "and EBA Guidelines on Fraud Reporting categories."
)


class PolicyAgent(Agent):
    name = "PolicyAgent"
    description = "Maps findings to PSD2 SCA exemptions and EBA reporting categories."
    tools = ["evaluate_sca"]

    async def _run(self, state: WorkflowState) -> AgentResult:
        amount = state.alert.amount or 0.0
        # Rough heuristic for cumulative spend — would be a real query in prod.
        cumulative = amount * 4
        channel = "card_not_present" if state.alert.device_id else "card_present"
        det = evaluate_sca_exemptions(amount, cumulative, channel)

        ctx = {
            "classification": state.classification.value,
            "alert": state.alert.model_dump(),
            "graph_summary": state.graph.model_dump() if state.graph else None,
            "deterministic_sca": det,
        }
        resp = await self.llm.chat(
            [
                LLMMessage("system", SYS),
                LLMMessage("user", json.dumps(ctx, default=str)),
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        parsed = self.parse_json(resp.get("content"))
        findings = PolicyFindings(
            sca_exemptions_applied=parsed.get("sca_exemptions_applied")
            or det["applied"],
            sca_exemptions_blocked=parsed.get("sca_exemptions_blocked")
            or det["blocked"],
            eba_categories=parsed.get("eba_categories")
            or self._default_eba(state.classification),
            rationale=parsed.get("rationale", ""),
        )
        state.policy = findings

        return AgentResult(
            agent=self.name,
            summary=(
                f"SCA applied={findings.sca_exemptions_applied} "
                f"blocked={findings.sca_exemptions_blocked} "
                f"EBA={findings.eba_categories}"
            ),
            data={"policy": findings.model_dump()},
            next_agent="NarrativeAgent",
            reason="policy mapping ready; narrative can now be drafted",
        )

    @staticmethod
    def _default_eba(c: Classification) -> list[str]:
        if c == Classification.SUSPECTED_FRAUD_RING:
            return ["organised_fraud", "fraud_card_not_present"]
        if c == Classification.ACCOUNT_TAKEOVER:
            return ["social_engineering", "fraud_credit_transfer"]
        if c == Classification.CARD_PRESENT_FRAUD:
            return ["fraud_card_present"]
        return []
