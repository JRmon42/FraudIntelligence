# ADR-0008 — Defender for Cloud + Purview + Azure Policy as the security/governance triad

> **Purpose.** Establish the standard control plane for security posture, data governance and sovereignty enforcement.

- **Status**: Accepted — 2025-03-12
- **Deciders**: CISO delegate, Chief Architect, Data Protection Officer

## Context

A high-risk AI system in five jurisdictions needs verifiable controls for:
- **Posture & threat detection** across compute, data, AI services.
- **Data discovery, classification, lineage** (GDPR Art 5/30, EU AI Act Art 10).
- **Preventive guardrails** for region pinning, networking, encryption, identity (sovereignty + DORA).

Options included third-party CNAPP (Wiz/Prisma) + Collibra + OPA, but procurement timelines and Azure-native integration tipped the balance.

## Decision

Adopt the Microsoft triad as **mandatory** for every subscription in scope:
- **Defender for Cloud P2** — CSPM standard, CWPP for Containers/Storage/Cosmos/Key Vault/AOAI/AML; auto-provision Defender agents; regulatory compliance dashboards = **PCI DSS 4.0 + ISO 27001 + NIS 2 + EU AI Act (preview)**.
- **Microsoft Purview** — scan OneLake, Cosmos, Storage, AML registry, Power BI; classification rules for PAN, IBAN, Nordic personnummer / personnumre / CPR / HETU / isikukood; lineage required from Bronze → Silver → Gold → semantic model.
- **Azure Policy** — initiative `NordicSovereignty v3` enforcing:
  - allowed regions = `swedencentral`, `northeurope` only (deny effect),
  - deny public network access on Cosmos/Storage/Key Vault/AOAI/AML,
  - require CMK on stateful resources,
  - require Private Endpoints,
  - require diagnostic settings to a regional Log Analytics workspace,
  - tag schema enforcement (`dataClassification`, `sovereignty`, `costCenter`, `aiActRole`).

## Consequences

**Positive**
- One pane of glass per concern, all integrated with Entra and Log Analytics.
- Sentinel ingests Defender + Purview + Policy compliance signals → unified SOC.
- Policy denies failed deployments **at create time**, not after.
- Regulatory dashboards generate evidence packs auditors actually accept.

**Negative**
- Purview scan cost grows with data volume; we scope scans to Silver+Gold + critical Cosmos containers, not raw Bronze.
- Defender alerts can be noisy initially; first 60 d include a tuning sprint with Sentinel analytics rules.
- Policy initiative changes require a controlled rollout (audit → deny) to avoid breaking existing pipelines.
