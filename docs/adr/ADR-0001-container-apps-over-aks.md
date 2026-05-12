# ADR-0001 — Use Azure Container Apps (not AKS) for the scoring API

> **Purpose.** Choose the compute substrate for the latency-critical `scoring-api`.

- **Status**: Accepted — 2025-02-14
- **Deciders**: Chief Architect, Platform Lead, SRE Lead
- **Supersedes**: n/a

## Context

The `scoring-api` must serve **5 k TPS sustained / 20 k TPS peak** at **p99 < 18 ms**, in two EU regions, with sub-30 s scale-out, mTLS east/west, and zero public data-plane exposure. The team is 14 engineers; we have no in-house Kubernetes platform team and don't want to operate one. We considered:

1. **AKS** with KEDA, Istio, Karpenter.
2. **Azure Container Apps** (ACA) — Consumption + Dedicated workload profiles.
3. **App Service for Containers** Premium v3.

Constraints: EU AI Act high-risk demands tight, auditable change management → fewer moving parts wins. Capex on Kubernetes operators (Istio CRDs, OPA gatekeeper, cert-manager, ingress controllers) directly competes with ML capacity.

## Decision

Use **Azure Container Apps** with a **Dedicated D8 workload profile** (8 vCPU / 32 GiB), `min_replicas = 3` per region, `max_replicas = 60`, KEDA scale rule on `concurrent-requests = 80`. Mesh provided by built-in Dapr/Envoy; mTLS enabled; revisions = `Multiple` for blue/green; ingress private + APIM in front.

## Consequences

**Positive**
- Zero K8s operator burden; revisions give native blue/green.
- Dedicated profile guarantees **no noisy-neighbour** (a true requirement for p99 SLO).
- Built-in **Workload Identity**, **Dapr**, **Key Vault refs**, **scale-to-zero** for non-prod.
- Faster CI/CD: `az containerapp update --revision-suffix` is one call.

**Negative / accepted trade-offs**
- ACA does not expose all CNI knobs (e.g., per-pod NSGs); mitigated by VNet integration + Private Endpoints.
- No direct DaemonSet pattern → sidecar logging via ACA built-in Log Analytics + App Insights instead.
- Dedicated workload profile is more expensive per vCPU than Consumption; modelled in cost plan.
- If we ever need GPU online inference, we'd revisit (currently CPU-only via ONNX — see [ADR-0002](./ADR-0002-onnx-in-process-scoring.md)).
