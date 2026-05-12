# PSD2 SCA Exemption Optimisation

> **Purpose.** Explain how the platform applies PSD2 RTS on Strong Customer Authentication (Commission Delegated Regulation (EU) 2018/389) exemptions per transaction to maximise frictionless flows while staying within EBA fraud-rate thresholds.

---

## 1. The problem

Every electronic payment in scope of PSD2 must carry SCA **unless** an exemption applies. Each unnecessary SCA challenge depresses authorisation rates by 5–12 % (industry data) and harms CX. Conversely, over-exempting raises fraud and breaches the **TRA fraud-rate thresholds** (Art 18 RTS), forcing an immediate ban on TRA at that exemption-rate band.

We need a **per-transaction decision** that picks the **lowest-friction lawful** exemption while keeping our **rolling 90-day fraud rate** well under the band cap.

---

## 2. Exemptions handled

| Exemption | RTS Art | Conditions (summary) | Where applied in our flow |
|---|---|---|---|
| **Transaction Risk Analysis (TRA)** | Art 18 | Real-time risk score below issuer/acquirer threshold; aggregate fraud rate within band caps (€100 → 13 bps; €250 → 6 bps; €500 → 1 bps). | **Primary** path — driven by ML score + rolling-fraud guard. |
| **Low-value** | Art 16 | ≤ €30 (remote); cumulative ≤ €100 / 5 tx since last SCA. | Counter kept in Cosmos `lvp_counters` per PAN-token. |
| **Trusted Beneficiaries** | Art 13 | Payee on cardholder's TB list at issuer, established with SCA. | Lookup against issuer TB list via internal API. |
| **Secure Corporate Payments** | Art 17 | B2B on dedicated secure protocols (lodge cards, virtual cards on corporate portals). | Flagged at acquirer level; passes through. |
| **Recurring transactions** | Art 14 | Same payee, same amount; first occurrence with SCA. | Detected by the **MIT/recurring classifier** in feature-builder. |
| **Merchant-Initiated Transactions (MIT)** | (Out of SCA scope under EBA Opinion) | Cardholder not in session, mandate established with SCA. | Tagged at scheme-data level (`MIT=Y`); not subject to SCA. |

(Out of scope: Art 11 contactless < €50, Art 12 unattended terminals — handled at terminal level, not by us.)

---

## 3. Decision flow

```
        ┌─────────── transaction envelope ───────────┐
        │ PAN-token, amount, MCC, channel, scheme tag │
        └──────────────────┬──────────────────────────┘
                           ▼
                 ┌─────────────────┐
                 │ Hard-gate rules │  (MIT? → exempt / out-of-scope)
                 └─────────┬───────┘
                           ▼
              ┌──────────────────────────┐
              │ Static exemption checks  │  (low-value, TB, secure-corp, recurring)
              └─────────────┬────────────┘
                            ▼
                ┌────────────────────────┐
                │ TRA optimiser (model)  │  inputs: ML fraud score, current
                │  + rolling-fraud guard │  rolling 90-d fraud rate per band,
                │                        │  amount band, issuer cap.
                └─────────────┬──────────┘
                              ▼
                  ┌────────────────────┐
                  │ Decision returned: │
                  │  EXEMPT(type) /    │
                  │  CHALLENGE(SCA)    │
                  └────────────────────┘
```

The decision is returned in the same `POST /v1/score` response under `exemption.type` and `exemption.reason`.

---

## 4. Rolling-fraud guard (TRA only)

To stay within the EBA TRA fraud-rate caps, the optimiser maintains rolling **90-day fraud rates per amount band** in Cosmos (`tra_metrics` container, partition by `country/band`, recomputed every 5 min by Stream Analytics from confirmed-fraud labels).

Hard guard rails:

| Band | EBA cap | Our internal trigger | Action when triggered |
|---|---|---|---|
| ≤ €100 | 13 bps | **9 bps** | TRA disabled for that band+country until back below 7 bps for 7 days |
| ≤ €250 | 6 bps | **4 bps** | as above |
| ≤ €500 | 1 bps | **0.7 bps** | as above |

Internal triggers sit ~30 % below the regulatory cap to give early warning. State of these guards is exposed on the Power BI **Risk** page, and breach generates a Sentinel incident routed to the Fraud Ops on-call.

---

## 5. Optimiser model

- **Inputs**: fraud score, amount, MCC, channel, country, device-trust, cardholder history, current rolling-fraud headroom per band.
- **Model**: gradient-boosted classifier producing P(challenge_required); tiny (< 1 MB) — runs in-process alongside the main scorer.
- **Calibration**: Platt-scaled per country quarterly.
- **Outputs**: chosen exemption type + confidence + counterfactual (would-be next-best exemption — captured for audit and EBA reporting).

---

## 6. Reporting & evidence

- Every exemption decision logged in `audit_scoring` (see EU AI Act Art 12 doc).
- Exemption coverage and resulting fraud rate are reported per quarter in the **EBA Q-report** (see [eba-fraud-reporting.md](./eba-fraud-reporting.md)).
- Power BI **SCA dashboard** shows: exemption mix, challenge-rate, authorisation-rate uplift, fraud rate per band per country, distance to internal trigger.

---

## TL;DR

We treat SCA exemption selection as an **optimisation under regulatory constraints**: a small in-process model picks the lowest-friction lawful exemption (favouring **TRA**, then static exemptions like low-value, trusted beneficiaries, recurring, secure-corporate, MIT). A **rolling-fraud guard** triggers **30 % below** EBA caps to keep TRA usage safe. Result: **73 % exemption coverage** with fraud rates well inside the EBA bands.
