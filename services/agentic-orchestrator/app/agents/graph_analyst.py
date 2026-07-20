"""GraphAnalystAgent — pulls a 2-hop neighbourhood from Cosmos Gremlin."""

from __future__ import annotations

from ..cosmos import BaseGraph
from ..state import AgentResult, WorkflowState
from ..tools import graph_two_hop
from .base import Agent


class GraphAnalystAgent(Agent):
    name = "GraphAnalystAgent"
    description = (
        "Traverses card/merchant/device graph to find suspicious neighbourhoods."
    )
    tools = ["graph_two_hop"]

    @property
    def graph(self) -> BaseGraph:
        return self.deps["graph"]

    async def _run(self, state: WorkflowState) -> AgentResult:
        a = state.alert
        findings = await graph_two_hop(
            self.graph,
            card_id=a.card_id,
            device_id=a.device_id,
            merchant_id=a.merchant_id,
        )
        state.graph = findings
        return AgentResult(
            agent=self.name,
            summary=(
                f"2-hop neighbourhood: {len(findings.nodes)} nodes / {len(findings.edges)} edges, "
                f"anomaly_score={findings.anomaly_score:.2f}"
            ),
            data={"graph": findings.model_dump()},
            next_agent="PolicyAgent",
            reason="graph context required before policy mapping",
        )
