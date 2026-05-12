"""CaseManagerAgent — opens / updates the case in Cosmos and writes timeline."""

from __future__ import annotations

from ..cosmos import BaseCases
from ..state import AgentResult, WorkflowState
from .base import Agent


class CaseManagerAgent(Agent):
    name = "CaseManagerAgent"
    description = "Persists the case record in Cosmos DB and maintains the timeline."
    tools = ["case_upsert", "case_get"]

    @property
    def cases(self) -> BaseCases:
        return self.deps["cases"]

    async def _run(self, state: WorkflowState) -> AgentResult:
        case = state.to_case()
        await self.cases.upsert(case)
        return AgentResult(
            agent=self.name,
            summary=f"case persisted: {case.case_id} (status={case.status})",
            data={"case_id": case.case_id, "status": case.status, "timeline_len": len(case.timeline)},
            next_agent="ReflectorAgent",
            reason="reflector should review the persisted case",
        )
