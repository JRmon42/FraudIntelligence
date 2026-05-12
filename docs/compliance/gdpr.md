# GDPR Mapping — Nordic Fraud Intelligence Platform

> **Purpose.** Map relevant GDPR articles to concrete platform controls and the evidence that demonstrates them, for use by the DPO, internal audit and supervisory authorities (SE IMY, NO Datatilsynet, DK Datatilsynet, FI Tietosuojavaltuutettu, EE AKI).

Scope: processing of cardholder data, device telemetry and merchant data for the purpose of **fraud prevention** (legitimate interest, GDPR Art 6(1)(f)) and **legal obligation** for AML/CTF reporting (Art 6(1)(c)).

---

## Article-by-article map

| Article | Requirement (summary) | Implementation in this platform | Evidence artefact |
|---|---|---|---|
| **Art 5 — Principles** | Lawfulness, fairness, transparency; purpose limitation; data minimisation; accuracy; storage limitation; integrity & confidentiality; accountability. | Purpose-bound processing (Purview classifications + Policy tags `purpose=fraud-prevention`); Bronze raw retained 90 d, Silver pseudonymised, Gold aggregated only; Cosmos TTL on features (90 d) and graph edges (365 d); CMK on every stateful service. | Purview lineage report, Policy compliance export, RoPA. |
| **Art 6 — Lawful basis** | A lawful basis is required. | Legitimate interest (LIA performed and signed) for scoring; Art 6(1)(c) for SAR/EBA reporting; consent **not** used for fraud. | Signed LIA in Confluence space `Norrsken/Legal`. |
| **Art 22 — Automated decisions** | Right not to be subject to a solely automated decision producing legal/significant effects, with safeguards (human review, contest, explanation). | Decline outcomes are **not solely automated**: AI score → rules engine → if `decision=DECLINE` and amount > €500 OR cross-border, the case enters **CaseManagerAgent** with mandatory human reviewer (Entra group `fraud-reviewers`). All declines carry **reason codes**; cardholder can contest via issuer's existing dispute channel. PolicyAgent enforces this gate. | Workflow diagram in `architecture.md` §4; reviewer audit log in Cosmos `cases` container; SK Process Framework state graph. |
| **Art 25 — Data protection by design & by default** | Embed DP into design and defaults. | Pseudonymisation at ingest (FPE on PAN before Bronze→Silver); tokenisation at acquirer edge; least-privilege via Entra PIM; private endpoints by default (Policy `deny`); telemetry sampling avoids storing full payloads beyond need. | Policy initiative `NordicSovereignty v3`; threat model in `docs/security/threat-model.md` (separate workstream). |
| **Art 32 — Security of processing** | Appropriate technical & organisational measures: encryption, confidentiality, integrity, availability, resilience, regular testing. | TLS 1.3 in transit + mTLS east-west; AES-256 at rest with **CMK in Key Vault Premium HSM**; Defender for Cloud P2 across all workloads; quarterly DR drill (Cosmos failover, EH geo-DR promotion); annual pen-test; Sentinel SOC 24/7. | DR drill reports; pen-test reports; Defender regulatory compliance dashboard. |
| **Art 33 — Breach notification** | Notify supervisory authority within 72 h. | Sentinel incident → severity classification → Logic App opens **breach-runbook** Playbook → DPO + CISO paged → 72 h timer in case tool. Templates pre-approved per jurisdiction (SE/NO/DK/FI/EE). | Sentinel playbook `pb-gdpr-breach`; runbook §"Breach response". |
| **Art 35 — DPIA** | Conduct DPIA for high-risk processing (this qualifies). | DPIA executed and signed; reviewed annually and on material change (e.g., new model class, new region). Includes necessity, proportionality, risk to data subjects, mitigations. | DPIA v2.1 in `docs/compliance/dpia.pdf` (out of scope for this repo, referenced). |
| **Art 44 — Transfers** | Transfers outside EEA require an adequacy mechanism. | **No transfers outside EEA.** Azure Policy denies non-EU regions; AOAI deployments restricted to EU data zone (Sweden Central + France Central); Microsoft EU Data Boundary in force; outbound traffic to non-EU IPs blocked at AFD/WAF level. NSG flow-logs reviewed monthly. | Policy compliance report; AFD WAF rule set; flow-log reviews. |

---

## Data-subject rights operationalisation

| Right | Mechanism |
|---|---|
| Access (Art 15) | DSAR portal (existing customer service) → triggers Logic App `lg-dsar` that joins Cosmos + Gold by `pan_token_hash` keyed lookup → returns redacted JSON within 30 d. |
| Rectification (Art 16) | Limited applicability (no profile data managed by us); upstream issuer system corrects, change propagates via CDC. |
| Erasure (Art 17) | Pseudonymisation key rotation makes historical Silver/Gold rows un-relinkable; raw Bronze deleted on schedule. |
| Restriction / Objection (Art 18, 21) | Objection routed to DPO; case-by-case review; legitimate-interest balancing recorded. |
| Portability (Art 20) | Out of scope (no contract or consent basis applies to fraud processing). |

---

## TL;DR

Lawful basis is **legitimate interest** (Art 6(1)(f)) for scoring and **legal obligation** (Art 6(1)(c)) for AML/EBA reporting. **Art 22** is satisfied by **mandatory human review** on material declines via the agentic workflow with reason codes and dispute path. **Art 32** is delivered by CMK + private endpoints + Defender + Sentinel; **Art 44** by EU-only deployment under the Microsoft EU Data Boundary, enforced by Azure Policy. DPIA is in place; breach response is automated to meet the 72 h clock.
