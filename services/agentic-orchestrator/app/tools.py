"""External tools made available to agents.

Each function is registered with Semantic Kernel as a kernel function so that
LLMs equipped with tool-calling can invoke them. We deliberately keep the
implementations side-effect-free where possible so they are trivially testable.
"""

from __future__ import annotations

from typing import Any

from .cosmos import BaseCases, BaseGraph
from .state import CaseRecord, GraphFindings


# ---------- Graph tools ----------

async def graph_two_hop(
    graph: BaseGraph,
    *,
    card_id: str | None = None,
    device_id: str | None = None,
    merchant_id: str | None = None,
) -> GraphFindings:
    """Pull a 2-hop neighbourhood around the alert anchors."""

    raw = await graph.two_hop(card_id=card_id, device_id=device_id, merchant_id=merchant_id)
    return GraphFindings(**raw)


# ---------- Case-store tools ----------

async def case_upsert(cases: BaseCases, case: CaseRecord) -> None:
    await cases.upsert(case)


async def case_get(cases: BaseCases, case_id: str) -> CaseRecord | None:
    return await cases.get(case_id)


# ---------- Policy tools (pure-python deterministic helpers) ----------

PSD2_SCA_EXEMPTIONS = {
    "low_value": "Article 16 — single transaction ≤ EUR 30 and cumulative ≤ EUR 100.",
    "trusted_beneficiary": "Article 13 — payee on the payer's trusted-beneficiary list.",
    "recurring": "Article 14 — recurring transactions of same amount/payee.",
    "corporate": "Article 17 — secure corporate payment processes.",
    "trx_risk_analysis": "Article 18 — TRA exemption thresholds (€100/€250/€500).",
}

EBA_CATEGORIES = [
    "fraud_card_present",
    "fraud_card_not_present",
    "fraud_credit_transfer",
    "fraud_direct_debit",
    "organised_fraud",
    "social_engineering",
]


def evaluate_sca_exemptions(amount_eur: float, cumulative_24h_eur: float, channel: str) -> dict[str, Any]:
    """Pure rule-based evaluation usable as a tool by the PolicyAgent."""

    applied: list[str] = []
    blocked: list[str] = []
    if amount_eur <= 30 and cumulative_24h_eur <= 100:
        applied.append("low_value")
    else:
        blocked.append("low_value")
    if channel == "card_not_present" and amount_eur > 500:
        blocked.append("trx_risk_analysis")
    if amount_eur > 100:
        blocked.append("trusted_beneficiary")
    return {"applied": applied, "blocked": blocked}


# ---------- Semantic Kernel registration ----------

def register_with_semantic_kernel(kernel: Any, *, graph: BaseGraph, cases: BaseCases) -> dict[str, Any]:
    """Register the tool surface with a Semantic Kernel kernel.

    Returns a metadata dict describing the registered tools (used by the
    ``GET /v1/agents`` endpoint).
    """

    metadata: dict[str, Any] = {}
    try:
        from semantic_kernel.functions import kernel_function

        @kernel_function(name="graph_two_hop", description="2-hop graph neighbourhood")
        async def _graph_two_hop(card_id: str = "", device_id: str = "", merchant_id: str = "") -> str:
            res = await graph_two_hop(
                graph,
                card_id=card_id or None,
                device_id=device_id or None,
                merchant_id=merchant_id or None,
            )
            return res.model_dump_json()

        @kernel_function(name="evaluate_sca", description="Evaluate PSD2 SCA exemptions")
        def _eval_sca(amount_eur: float, cumulative_24h_eur: float, channel: str) -> str:
            import json

            return json.dumps(evaluate_sca_exemptions(amount_eur, cumulative_24h_eur, channel))

        try:
            kernel.add_plugin(
                {"graph_two_hop": _graph_two_hop, "evaluate_sca": _eval_sca},
                plugin_name="fraud_tools",
            )
        except Exception:
            # Older / newer SK APIs differ — fall back silently; tools still
            # callable directly by Python agents.
            pass

        metadata = {
            "graph_two_hop": "Cosmos Gremlin 2-hop traversal",
            "evaluate_sca": "PSD2 SCA exemption evaluator",
        }
    except Exception:
        metadata = {"graph_two_hop": "(SK unavailable — direct python only)"}
    return metadata
