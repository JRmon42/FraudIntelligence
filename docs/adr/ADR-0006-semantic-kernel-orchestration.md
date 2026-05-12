# ADR-0006 — Semantic Kernel for multi-agent orchestration with state graph + reflection

> **Purpose.** Choose the agent framework that drives Triage → GraphAnalyst → Policy → CaseManager → Narrative.

- **Status**: Accepted — 2025-03-07
- **Deciders**: ML Lead, App Lead, Chief Architect

## Context

The case-management workflow benefits from autonomous-but-bounded agents:
- **TriageAgent** — cluster the alert, pick severity.
- **GraphAnalystAgent** — explore Cosmos Gremlin neighbourhood, summarise ring topology.
- **PolicyAgent** — apply jurisdiction rules (PSD2/EBA/national).
- **CaseManagerAgent** — open/update case in the case store.
- **NarrativeAgent** — draft SAR or EBA narrative for human reviewer.

Options:
1. **Microsoft Semantic Kernel** (MSFT-supported, .NET + Python, plugin model, recently added **Process Framework** state graph + filters/reflection).
2. **LangGraph** (LangChain ecosystem).
3. **AutoGen** (msft-research).
4. Hand-rolled state machine on Durable Functions.

## Decision

Use **Semantic Kernel (Python 1.10+)** with the **Process Framework** to model the agent flow as an explicit **state graph** (nodes = agents, edges = events), with:
- **Reflection step** after each agent that checks output against a JSON schema and Responsible-AI guardrail prompt; on failure, retry once then escalate to a human reviewer.
- **Plugins** for Cosmos Gremlin, Cosmos SQL, Purview lineage lookup, Power Automate (for SAR submission), Sentinel (for IoC enrichment).
- **Workload Identity** to AOAI; **prompt + completion logged** to a tamper-evident store (Cosmos with append-only stored proc + Storage immutable blob backup).

## Consequences

**Positive**
- First-party MSFT support → procurement and security review path is short.
- Explicit state graph = auditable workflow (EU AI Act Art 12 + Art 14 human-oversight).
- Plugin model maps cleanly to our existing Azure SDKs.

**Negative**
- Semantic Kernel Process Framework is newer than LangGraph; we pin to a specific minor version and maintain a thin abstraction layer to swap if needed.
- Reflection adds cost (extra completion call); budgeted and capped per case.
- Multi-language SK (Python + .NET) means we standardise on **Python only** for this service to avoid skill split.
