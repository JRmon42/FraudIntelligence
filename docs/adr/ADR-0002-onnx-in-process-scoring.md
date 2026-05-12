# ADR-0002 — ONNX Runtime in-process scoring for sub-18 ms p99

> **Purpose.** Pick the model-serving topology that meets the p99 < 18 ms SLO.

- **Status**: Accepted — 2025-02-18
- **Deciders**: ML Lead, Platform Lead, Chief Architect

## Context

End-to-end p99 budget is 18 ms. Network round-trip to a separate model server (Azure ML managed online endpoint, Triton on AKS, KServe, etc.) eats 4–8 ms before any inference happens. Our model is a **LightGBM ensemble + small GNN-embedding lookup** (~14 MB total) — easily co-locatable in the API process.

Options evaluated:
1. **Azure ML managed online endpoint** (separate deployment).
2. **Triton Inference Server** as ACA sidecar.
3. **ONNX Runtime in-process** inside the FastAPI worker.

Benchmarked on STANDARD_D8_v5: in-process ORT median **3.8 ms / p99 6.4 ms**; sidecar +HTTP +2.2 ms p99; Azure ML endpoint +6.1 ms p99 + extra failure modes.

## Decision

Convert ensemble + GNN-embedding head to **ONNX (opset 18)**, ship as a layer in the scoring-api container, load with **onnxruntime 1.18 (CPU EP, intra-op-threads=4, graph optimizations=ALL)** at process start. Models are pulled at build-time from **AML Model Registry** (immutable tag) and signed with cosign.

Azure ML **managed online endpoint remains as a fallback** path (5 % shadow traffic) for the rare case where in-proc loading fails and to anchor the model versioning story.

## Consequences

**Positive**
- Removes a network hop and a separate deployment from the hot path.
- Deterministic resource accounting (no cross-tenant noise).
- Model promotion = container image promotion → one CI/CD path, one audit trail (good for EU AI Act Art 12 record-keeping).

**Negative**
- API container size grows by ~80 MB; mitigated by multi-stage build + slim base.
- Model rollback = revision rollback (acceptable; covered in `runbook.md`).
- GPU upgrade path requires re-architecture (we accept — current models are CPU-friendly).
- We must guard memory: ORT session is preloaded once per worker; uvicorn `--workers 4` with explicit warm-up endpoint hit during ACA `startupProbe`.
