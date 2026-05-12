# Power BI — EBA Fraud Dashboard

PBIP project for the FraudIntelligence Executive / EBA / Operational dashboards.

## Project layout

```
powerbi/
├── eba_fraud_dashboard.pbip/
│   ├── .pbip                                     # PBIP project descriptor
│   └── definition/
│       ├── report.json                           # Report-level config + global filters
│       ├── model.bim                             # Tabular semantic model (TMSL)
│       └── pages/
│           ├── ExecutiveOverview.json            # Page 1
│           ├── EbaQuarterlyReport.json           # Page 2 (filterable by instrument)
│           └── Operational.json                  # Page 3
├── measures.dax                                  # All DAX measures (mirrors model.bim)
├── dataset_schema.md                             # Tables / columns / types / source
└── README.md
```

## Semantic model

**Storage mode:** Direct Lake on the Fabric Lakehouse `lh_fraud` — no scheduled
refresh required for fact tables; dimensions are imported (small).

**Star schema:**

```
                        Dim_Date
                            |
   Dim_Country ── Fact_Tx ──┴── Dim_Instrument
                            |
   Dim_Exemption ── Fact_Eba ── Dim_FraudType
                            |
                  Fact_Exemption       Fact_Latency
```

See [`dataset_schema.md`](./dataset_schema.md) for column-level detail.

## Pages

| # | Page | Notes |
|---|---|---|
| 1 | Executive overview | Fraud loss €, decline rate, scoring p99, PSD2 mix, by country |
| 2 | EBA quarterly report | Annexes A–D, **filterable by instrument type** + quarter |
| 3 | Operational | Alerts, cases, agent performance, model drift |

Every page carries a **country filter** pre-scoped to SE/NO/DK/FI/EE.

## Refresh

* **Direct Lake** facts: no refresh — Power BI reads Delta files in OneLake
  directly. End-to-end freshness is bounded by the medallion pipeline (hourly).
* **Imported dimensions**: refreshed daily at 02:30 UTC after `30_gold_marts`
  completes.
* Configure the refresh in the Fabric workspace settings → Schedule refresh:

  ```
  Frequency: Daily
  Time:      02:30 UTC
  Email on failure: data-eng@fraudintelligence.example
  ```

## Publish

```bash
# 1. Open the .pbip in Power BI Desktop (April 2024+)
# 2. Sign in with a workspace identity that has Member rights on ws-fi-prod
# 3. File > Publish > Workspace: ws-fi-prod
#
# Or via fabric-cli / Azure DevOps:
az fabric report deploy \
    --workspace ws-fi-prod \
    --pbip ./eba_fraud_dashboard.pbip
```

## Row-level security

The semantic model ships with one role:

| Role | Filter |
|------|--------|
| `Country Reader` | `Dim_Country[CountryCode] = USERPRINCIPALNAME().country_claim` |

Country claims are issued by Entra ID conditional access policies — analysts
in the Swedish team see SE only, NCA auditors see all five.

## Source-of-truth contract with `eba-reporter`

The dashboard's Annex C measure ([`EBA Annex C Fraud Rate (bps)`]) and the
basis-points value rendered in the XLSX submitted to NCAs **must** match.
A nightly DAX query (Fabric notebook `99_dashboard_recon.ipynb` — out of scope
for this PR) compares the two; any drift > 1 bps fails the deployment.
