# ADR-0003 — Cosmos DB (multi-master) as feature store + graph store (Gremlin API)

> **Purpose.** Choose the state store for low-latency feature lookups and 1-hop graph traversals on the hot path.

- **Status**: Accepted — 2025-02-21
- **Deciders**: Data Lead, Platform Lead, Chief Architect

## Context

The hot path needs:
- **Point-reads < 5 ms p99** for feature vectors keyed by PAN-token / device / merchant.
- **1-hop graph traversal < 5 ms p99** on the entity graph (PAN ↔ device ↔ merchant ↔ IP).
- **Multi-region writes** so SE-issued cards transacting in DK don't pay a cross-region write hop.
- Strong durability + **PITR** for forensic replay (EBA + EU AI Act Art 12).

Options:
1. **Cosmos DB** SQL API + **Cosmos Gremlin API** (separate containers, same account).
2. **Azure SQL HyperScale** + **Neo4j AuraDB on Azure**.
3. **Redis Enterprise (RedisGraph)** as the source of truth.

## Decision

Use **Azure Cosmos DB** with **multi-region writes** (SE Central + North Europe), autoscale **50 k → 400 k RU/s**, two APIs in the same account:
- `SQL API` container `features` (partition key `/pan_token_hash`, TTL 90 d).
- `Gremlin API` graph `entity_graph` (partition key `/country`, edges retained 365 d).
- Conflict resolution: **LWW on `eventTimeUtc`** for features; **custom merge stored proc** for graph edges (additive).
- **CMK (BYOK)** via Key Vault Premium HSM, per-region keys.
- **Private Endpoints only**, no public ingress.
- Redis Enterprise sits **in front** as a read-through cache for the very hottest 1 % of keys.

## Consequences

**Positive**
- One vendor, one billing, one IaC module for both feature and graph workloads.
- Multi-master = zero cross-region write latency; survives regional loss with RPO 0.
- 99.999 % SLA with multi-region writes.
- Native PITR (30 d) covers forensic + auditor asks.

**Negative**
- Gremlin API has fewer features than Neo4j Cypher (no advanced path algorithms server-side). Mitigation: heavy graph analytics (community detection, GNN training) run **offline** on Fabric Spark — Gremlin only serves **1-hop** at runtime.
- RU cost modelling is non-trivial; we instrument every query with `x-ms-request-charge` to App Insights and alert on regression > 10 %.
- LWW conflict policy means we accept rare lost feature updates < 50 ms apart; analysed and acceptable for fraud features (next event refreshes them anyway).
