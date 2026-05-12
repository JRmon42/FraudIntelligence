# EU AI Act Compliance — Nordic Fraud Intelligence Platform

> **Purpose.** Demonstrate that the platform meets the obligations applicable to **high-risk AI systems** under Regulation (EU) 2024/1689 (the EU AI Act), classified under **Annex III §5(b)** (AI systems intended to evaluate the creditworthiness of natural persons or to be used for risk assessment in financial services that affect access to essential services).

Although fraud scoring is not "credit scoring" in the classical sense, a decline materially affects a natural person's access to a financial service (the ability to pay). We treat the system as **high-risk** out of an abundance of caution and to align with the customer's risk appetite and Finansinspektionen guidance.

**Provider role**: the customer (the Nordic payments provider). Microsoft provides components but is not the AI Act provider for this composed system.

---

## Article-by-article implementation

### Art 9 — Risk Management System (RMS)
- Continuous, documented RMS owned by the **AI Risk Committee** (CRO chair, CISO, DPO, Head of Fraud, ML Lead).
- Risks enumerated in `docs/compliance/airm-register.xlsx` (out-of-repo): bias, drift, adversarial evasion, automation bias, model collapse, third-party dependency.
- Mitigations linked to controls in this repo (e.g., drift → Evidently dashboards + AML monitoring; adversarial → input validation + rate limiting at AFD/WAF).
- Reviewed quarterly; triggered on every material change (new region, new model family).

### Art 10 — Data and Data Governance
- Training, validation and test sets sourced from Silver layer; **stratified by country and instrument type**; labelled by confirmed-fraud feedback loop with a 60-day quarantine to avoid label leakage.
- **Bias testing**: false-positive rate parity checked across age band, country, merchant category — published in the model card; threshold for promotion = ≤ 10 % FPR delta across protected groups.
- Data lineage end-to-end via **Purview**; pseudonymisation of PII before ML access.
- Synthetic augmentation only for rare-fraud patterns (CTGAN), tagged and tracked separately.

### Art 11 — Technical Documentation (Annex IV)
- Maintained in `docs/` and the **Azure ML Model Registry** model card. Includes:
  - System purpose, intended use, foreseeable misuse;
  - Architecture (`docs/architecture.md`) and component versions;
  - Training data description, preprocessing, feature list, hyper-parameters;
  - Performance metrics (precision/recall/AUC by country, FPR parity);
  - Limitations and known failure modes;
  - Human oversight measures and reviewer instructions.
- Frozen at every model release; PR-reviewed; stored immutably (Storage with **Immutable Blob policy**).

### Art 12 — Record-Keeping (Logs)
- **Append-only event store** of every scoring request and decision in Cosmos `audit_scoring` (writes via stored proc that rejects updates), backed up nightly to **Storage with Immutable Blob (WORM, 7 yr)**.
- Captured fields: `requestId`, `modelVersion`, `featureHash`, `score`, `decision`, `reasonCodes[]`, `exemptionApplied`, `latencyMs`, `region`, `reviewerId` (if applicable).
- Agent prompts/completions logged with the same retention.

### Art 13 — Transparency & Information to Deployers
- The deployer (the payments provider's fraud-ops team) receives:
  - Model card with intended use, performance, limitations;
  - Operating manual (`docs/runbook.md`);
  - Reason-code dictionary used in declines and SAR narratives;
  - Disclosure copy for cardholder-facing comms ("an automated check has flagged...").
- **Content provenance**: AI-generated narratives are tagged `ai_generated=true` and watermarked in metadata; final SAR is human-signed.

### Art 14 — Human Oversight
- **Designed-in** oversight, not bolted on:
  - Material declines → human review (Art 22 GDPR alignment, see `gdpr.md`).
  - Agentic workflow has explicit **stop / override / escalate** controls in the case-management UI.
  - Reviewers are **trained and certified** (annual refresher, recorded in HRIS).
  - **Kill switch**: AML endpoint feature flag + AFD rule can route 100 % to a deterministic rules-only fallback within 60 s.

### Art 15 — Accuracy, Robustness, Cybersecurity
- **Accuracy**: monitored continuously (Evidently + AML); per-country dashboards; model promotion gate = no metric regression > 2 % vs champion.
- **Robustness**: input validation (schema + range), adversarial test suite in `tests/adversarial/`, fallback to rules engine on inference error.
- **Cybersecurity**: signed container images (cosign), SBOM (Syft) in CI, dependency scanning (Defender for DevOps), Private Endpoints + mTLS, Defender for AI workloads, prompt-injection guards on LLM inputs (Azure AI Content Safety + custom regex).
- Annual **red-team** including model-evasion and LLM jailbreak scenarios.

### Conformity assessment (Art 43)
- Internal control conformity assessment (Annex VI) — high-risk Annex III system relying on harmonised standards (ISO/IEC 42001, ISO/IEC 23894, ISO/IEC 5338) where available.
- **Declaration of Conformity** signed by the provider before placing on market / putting into service; CE marking applied to the system documentation.
- Registration in the **EU database for high-risk AI systems** (Art 49) before go-live.

### Post-market monitoring (Art 72)
- Post-Market Monitoring Plan in `docs/compliance/pmm-plan.md` (out of repo): KPIs, drift thresholds, incident triggers, reporting cadence.
- Continuous metrics piped to Power BI **Risk dashboard**; drift alerts → AI Risk Committee within 24 h.
- **Serious-incident reporting** to the relevant national market-surveillance authority within 15 days (Art 73), automated draft via NarrativeAgent.

---

## Roles & responsibilities (summary)

| Role | Owner |
|---|---|
| Provider (AI Act) | Customer (Nordic payments provider) |
| AI Risk Committee chair | CRO |
| Model owner | ML Lead |
| Reviewer pool | Fraud Operations |
| DPO | DPO |
| Conformity assessment sign-off | CRO + CISO + DPO |

---

## TL;DR

The platform is treated as a **high-risk AI system (Annex III §5(b))**. Every Article 9–15 obligation has a concrete control implemented in Azure: Purview lineage + bias testing for Art 10; immutable Cosmos+WORM logs for Art 12; mandatory human review with kill-switch for Art 14; signed images, SBOM and red-team for Art 15. Internal conformity assessment, EU-database registration and post-market monitoring close the loop.
