# `/agents/` — pointer

This folder is intentionally empty. The runtime agents that make up the
**Heimdall agentic orchestrator** live with their service code:

```
services/agentic-orchestrator/app/agents/
```

## The 6 production agents (Semantic Kernel)

| File | Agent | Responsibility |
|------|-------|----------------|
| [`base.py`](../services/agentic-orchestrator/app/agents/base.py)              | `BaseAgent`         | Shared LLM client, tool registration, telemetry |
| [`triage.py`](../services/agentic-orchestrator/app/agents/triage.py)          | `TriageAgent`       | Initial classification of alerts coming from the scoring API |
| [`graph_analyst.py`](../services/agentic-orchestrator/app/agents/graph_analyst.py) | `GraphAnalystAgent` | Mule-ring / fan-out detection using GraphSAGE embeddings |
| [`policy.py`](../services/agentic-orchestrator/app/agents/policy.py)          | `PolicyAgent`       | PSD2 SCA optimisation + EU AI Act high-risk decisioning |
| [`case_manager.py`](../services/agentic-orchestrator/app/agents/case_manager.py) | `CaseManagerAgent`  | Case lifecycle, hand-off to investigators, EBA reporting trigger |
| [`narrative.py`](../services/agentic-orchestrator/app/agents/narrative.py)    | `NarrativeAgent`    | LLM-generated investigator-friendly explanation |
| [`reflector.py`](../services/agentic-orchestrator/app/agents/reflector.py)    | `ReflectorAgent`    | Self-critique loop, drift / hallucination detection |

## How they collaborate

The orchestrator (`services/agentic-orchestrator/app/orchestrator.py`) wires
the agents into a **state-graph planner** with a reflection loop:

```
Alert  →  Triage  →  GraphAnalyst  →  Policy  →  CaseManager
                                  ↘                  ↑
                                   Narrative ────────┘
                                       ↑
                                  Reflector (critique → replan)
```

State, tool calls, token usage, and reflection iterations are emitted as
OpenTelemetry spans to Application Insights for full traceability — see
[`docs/architecture.md`](../docs/architecture.md) §“Agentic layer”.

## Local dev

```bash
cd services/agentic-orchestrator
pip install -e .
pytest                                 # 15 unit tests
python -m app.main                     # local FastAPI on :8081
```

## Deployment

The orchestrator is packaged as a container and deployed to **Azure
Container Apps** by [`infra/modules/containerapps.bicep`](../infra/modules/containerapps.bicep)
under the app name `aca-fraudintel-orchestrator-<env>-<region>`.
