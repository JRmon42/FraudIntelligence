# ADR-0007 — Azure OpenAI gpt-4o-mini for narratives, gpt-4o for complex case reasoning

> **Purpose.** Split LLM workloads to balance cost, latency and reasoning quality.

- **Status**: Accepted — 2025-03-10
- **Deciders**: ML Lead, FinOps Lead, Chief Architect

## Context

Two distinct LLM workloads:
- **High-volume narratives** — SAR/EBA draft text from structured case JSON. Schema-constrained, low ambiguity, high volume (~3 k/day).
- **Complex case reasoning** — agent reasoning over multi-hop graph evidence, conflicting policy rules, ambiguous merchant data. Lower volume (~150/day) but accuracy-critical.

Using `gpt-4o` for both is ~6× cost; using `gpt-4o-mini` for both fails on the complex cases (qualitative regression in eval set).

## Decision

- **`gpt-4o-mini`** (PTU + pay-as-you-go fallback) for **NarrativeAgent** and **TriageAgent** — schema-constrained outputs, JSON-mode + structured outputs.
- **`gpt-4o`** (PTU only) for **GraphAnalystAgent** and **PolicyAgent** when triage severity ≥ HIGH or graph node-count > 50.
- **Model router** = small SK function with explicit thresholds (no learned routing — auditable).
- Both deployments in **EU data zone** (Sweden Central primary, France Central secondary).
- **Content filters**: default Azure OpenAI safety + custom blocklist for PAN/IBAN regex.

## Consequences

**Positive**
- ~70 % cost reduction vs all-gpt-4o, with no measurable narrative-quality drop.
- PTU on gpt-4o gives deterministic latency for the rare-but-important reasoning calls.
- Auditable router (no opaque model selection — required for EU AI Act Art 13 transparency).

**Negative**
- Two model lifecycles to manage (eval, drift, deprecation).
- PTU capacity must be sized for peaks; we keep pay-as-you-go burst on `gpt-4o-mini` only.
- If OpenAI deprecates gpt-4o-mini, NarrativeAgent must be re-evaluated; we keep an eval harness in `tests/llm-eval/`.
