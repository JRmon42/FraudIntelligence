# ADR-0004 — Event Hubs + Stream Analytics over self-managed Kafka/Flink

> **Purpose.** Choose the streaming backbone and stream processor.

- **Status**: Accepted — 2025-02-25
- **Deciders**: Data Lead, SRE Lead, Chief Architect

## Context

We must ingest ~**130 k events/sec peak**, fan-out to multiple consumers (Cosmos hot aggregates, OneLake Bronze, agentic triage queue), provide **geo-DR**, and integrate cleanly with Fabric and Cosmos. Options:

1. **Event Hubs Dedicated** + **Stream Analytics** (managed).
2. **Confluent Cloud Kafka** + **Apache Flink on AKS**.
3. **HDInsight Kafka** + **Flink on AKS**.

The team has 1.5 streaming-specialist FTE. EU AI Act + DORA push us toward **fewer self-operated** components.

## Decision

Use:
- **Event Hubs Dedicated** (Cluster Units = 2 in SE, 1 in NE), **Kafka-protocol enabled** (so future migration is open), **geo-DR alias** `eh-fraud-prod`, **Capture** to OneLake disabled (we use ASA → Bronze instead, for schema control).
- **Azure Stream Analytics** SU=12, dedicated cluster, jobs:
  - `asa-hot-aggregates` → Cosmos
  - `asa-bronze-sink` → OneLake delta
  - `asa-anomaly` → triage queue (Service Bus)
- **Schema Registry**: Event Hubs built-in (Avro), enforced in producers.

## Consequences

**Positive**
- Zero broker ops; geo-DR is a single ARM toggle.
- ASA SQL-like jobs reviewable by analysts (auditable transformation logic — useful for EU AI Act Art 11).
- Kafka protocol surface keeps the door open if/when we outgrow ASA.

**Negative**
- ASA lacks the expressive power of Flink (no sophisticated CEP libraries). Mitigation: rare complex patterns are handled by the **agentic orchestrator** downstream, not in stream.
- Event Hubs Dedicated is expensive at low load. Mitigation: cost-modelled against expected baseline; non-prod uses Standard tier.
- Geo-DR is **not** active/active for streams — failover is a **manual promotion** (covered in `runbook.md`).
