"""Offline demo: run the canonical fraud-ring scenario end-to-end.

Usage::

    python -m app.demo
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .agents import build_default_agents
from .cosmos import build_cases, build_graph
from .llm import build_llm
from .planner import Planner
from .state import Alert, WorkflowState


SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_alert.json"


async def main() -> None:
    alert_payload = json.loads(SAMPLE.read_text())
    alert = Alert(**alert_payload)

    llm = build_llm(mock=True)
    cases = build_cases(mock=True)
    graph = build_graph(mock=True)
    agents = build_default_agents(llm, graph=graph, cases=cases)
    planner = Planner(agents)

    state = WorkflowState(alert=alert, reflection_budget=2)
    print(f"\n=== Heimdall Agentic Orchestrator — DEMO ===")
    print(f"Alert: {alert.alert_id} amount={alert.amount} {alert.currency} reasons={alert.reason_codes}\n")

    await planner.run(state)

    print("--- Timeline ---")
    for i, t in enumerate(state.timeline, 1):
        print(f"{i:>2}. [{t.ts}] {t.agent:<20} {t.action}")
    print(f"\nFinal classification: {state.classification.value}")
    print(f"Reflections used   : {state.reflections_used}/{state.reflection_budget}")
    print(f"Verdict            : {state.reflection_verdict.value if state.reflection_verdict else 'n/a'}")
    print(f"Visited agents     : {' -> '.join(state.visited)}")

    if state.narrative_sar:
        print("\n--- SAR (excerpt) ---")
        print(state.narrative_sar[:600])
    if state.narrative_eba:
        print("\n--- EBA narrative (excerpt) ---")
        print(state.narrative_eba[:400])


if __name__ == "__main__":
    asyncio.run(main())
