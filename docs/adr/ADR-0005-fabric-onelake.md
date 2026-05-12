# ADR-0005 — Microsoft Fabric (OneLake) over Synapse-only for unified analytics

> **Purpose.** Choose the lakehouse + BI platform for offline analytics, GNN training data, and EBA reporting.

- **Status**: Accepted — 2025-03-03
- **Deciders**: Data Lead, BI Lead, Chief Architect

## Context

We need:
- A single **medallion lake** (Bronze/Silver/Gold) consumable by Spark, KQL, T-SQL and Power BI.
- **OneLake shortcuts** to share Gold to the BI tenant without copies.
- Tight coupling to **Power BI Premium** for EBA paginated reports.
- A path for **Direct Lake** semantic models (no import refresh).

Options:
1. **Microsoft Fabric F64** (OneLake + Spark + KQL + Warehouse + Power BI Premium under one capacity).
2. **Synapse Analytics** (dedicated SQL pool + Spark pool) + ADLS Gen2 + Power BI Premium separately.
3. **Databricks** + Unity Catalog + Power BI.

## Decision

Adopt **Microsoft Fabric F64** as the unified analytics plane. Workspaces:
- `ws-fraud-bronze` — landing from ASA, delta parquet, no transformations.
- `ws-fraud-silver` — cleansed, pseudonymised, joined to dims; Purview-scanned.
- `ws-fraud-gold` — EBA-aligned facts, served via **Direct Lake** semantic model.
- `ws-fraud-ml` — feature-engineering notebooks + AML pipeline triggers.

OneLake CMK with Key Vault keys; **Purview** governance on every workspace; **Fabric Domains** = `fraud`, `risk`, `regulatory`.

## Consequences

**Positive**
- Single capacity to budget; fewer cross-service auth headaches.
- Direct Lake removes the import-refresh window — EBA dashboards always fresh.
- OneLake shortcuts let Risk and Finance consume Gold **without copies** (GDPR data-minimisation friendly).
- Native Git integration on Fabric items → ADRs, notebooks and pipelines all PR-reviewed.

**Negative**
- Fabric is younger than Synapse; some Synapse-specific features (e.g., advanced dedicated SQL pool tuning) are not 1:1. Acceptable — our Gold queries are well-bounded.
- Capacity bursting can be expensive if not governed; mitigated by **Fabric Capacity Metrics** + Azure Monitor alerts.
- Multi-region: F64 is region-pinned. For DR we replicate Gold delta to North Europe via shortcut + scheduled snapshot.
