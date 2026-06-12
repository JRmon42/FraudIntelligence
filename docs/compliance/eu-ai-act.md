# EU AI Act Compliance — Nordic Heimdall Platform

> **Purpose.** Document how the platform is governed under Regulation (EU) 2024/1689 (the EU AI Act). Fraud detection is **excluded from *mandatory* high-risk classification** by the **Annex III §5(b) financial-fraud carve-out** ("…evaluate the creditworthiness of natural persons… *with the exception of AI systems used for the purpose of detecting financial fraud*"). The provider nonetheless **voluntarily** governs the system to **high-risk-equivalent** standards — implementing the Annex III high-risk obligations (Art 9–15) as internal controls.

This voluntary posture reflects the customer's risk appetite and Finansinspektionen alignment: a decline materially affects a natural person's access to a financial service, so the provider chooses to meet high-risk-grade controls even though they are not legally mandated for this use case. The carve-out removes the *mandatory high-risk* obligations and conformity-assessment/registration duties — it does **not** remove the Act's general transparency and governance expectations.

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

### Conformity assessment (Art 43) — *voluntary*

Because the fraud-detection carve-out removes the **mandatory** high-risk obligations, the following are performed **voluntarily** as internal governance, not as legally required market-placement duties:
- Internal control conformity assessment (Annex VI) — high-risk-equivalent system relying on harmonised standards (ISO/IEC 42001, ISO/IEC 23894, ISO/IEC 5338) where available.
- **Declaration of Conformity** signed internally by the provider before putting into service; documentation maintained to high-risk standard. (CE marking and the Art 49 **EU high-risk database registration** are tracked as voluntary readiness measures and would only become mandatory if the use case were re-scoped outside the fraud carve-out.)

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

The platform is governed to **high-risk-equivalent** standards **voluntarily** — fraud detection is excluded from *mandatory* high-risk classification by the **Annex III §5(b) financial-fraud carve-out**, but the provider implements every Article 9–15 obligation as a concrete Azure control: Purview lineage + bias testing for Art 10; immutable Cosmos+WORM logs for Art 12; mandatory human review with kill-switch for Art 14; signed images, SBOM and red-team for Art 15. Internal conformity assessment, EU-database readiness and post-market monitoring close the loop as voluntary measures.
