"""NarrativeAgent — drafts SAR + EBA narratives via Azure OpenAI gpt-4o."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..llm import LLMMessage
from ..state import AgentResult, WorkflowState
from .base import Agent


SYS = (
    "AGENT: NarrativeAgent. You draft regulator-grade narratives. "
    "Return JSON {sar:'...', eba:'...'} where sar is a Suspicious Activity Report "
    "and eba is the EBA fraud-reporting narrative. Use Markdown. Be precise, "
    "cite figures from the supplied context, never invent identifiers."
)


class NarrativeAgent(Agent):
    name = "NarrativeAgent"
    description = "Drafts SAR and EBA reporting narratives from the consolidated case state."
    tools: list[str] = []

    async def _run(self, state: WorkflowState) -> AgentResult:
        ctx = {
            "alert": state.alert.model_dump(),
            "classification": state.classification.value,
            "graph": state.graph.model_dump() if state.graph else None,
            "policy": state.policy.model_dump() if state.policy else None,
        }
        resp = await self.llm.chat(
            [LLMMessage("system", SYS), LLMMessage("user", json.dumps(ctx, default=str))],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        parsed = self.parse_json(resp.get("content"))

        sar_tmpl = parsed.get("sar", "")
        eba_tmpl = parsed.get("eba", "")
        # Mock LLM returns format placeholders; render them.
        fmt_kwargs = {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "n_cards": sum(1 for n in (state.graph.nodes if state.graph else []) if n.get("label") == "card"),
            "merchant_id": state.alert.merchant_id or "(unknown)",
            "device_id": state.alert.device_id or "(unknown)",
            "amount": state.alert.amount or 0.0,
            "currency": state.alert.currency,
            "n_nodes": len(state.graph.nodes) if state.graph else 0,
            "anomaly_score": state.graph.anomaly_score if state.graph else 0.0,
        }
        try:
            sar = sar_tmpl.format(**fmt_kwargs)
        except (KeyError, IndexError):
            sar = sar_tmpl
        try:
            eba = eba_tmpl.format(**fmt_kwargs)
        except (KeyError, IndexError):
            eba = eba_tmpl

        state.narrative_sar = sar
        state.narrative_eba = eba
        return AgentResult(
            agent=self.name,
            summary=f"narratives drafted (sar={len(sar)}b, eba={len(eba)}b)",
            data={"sar_len": len(sar), "eba_len": len(eba)},
            next_agent="CaseManagerAgent",
            reason="persist updated case before reflection",
        )
