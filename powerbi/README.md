# Power BI — EBA Fraud Dashboard

PBIP project for the Heimdall Executive / EBA / Operational dashboards.

> **⚠️ Two project variants in this folder**
>
> * **`eba_fraud.pbip`** + `eba_fraud.Report/` + `eba_fraud.SemanticModel/` — **the openable project.**
>   Open *this* one in Power BI Desktop. It is a valid PBIP whose report is stored in the
>   modern **PBIR enhanced format** (`eba_fraud.Report/definition/` folder with one
>   `visual.json` per visual, plus `page.json`/`pages.json`/`report.json`/`version.json`);
>   `definition.pbir` (version 4.0) links the semantic model by path. All 21 visuals across
>   the 3 pages and the `model.bim` semantic model are preserved, and every PBIR file is
>   validated against the official Microsoft JSON schemas.
>   Its fact tables are **import mode with inline sample data** (the Direct Lake
>   `entity` partitions cannot be loaded in local Desktop), so the dashboard opens
>   and renders standalone for demos. The real Direct Lake model lives in the
>   mockup folder below and on the Fabric workspace.
> * **`eba_fraud_dashboard.pbip/`** (folder) — the original hand-authored **mockup**.
>   It is **not** a valid PBIP (it declares new-PBIR page schemas but uses legacy
>   `visualContainers` content, and its `.pbip` lists a `dataset` artifact that
>   current Desktop rejects). Kept for reference only — do not try to open it.
>
> The openable variant is generated from the mockup; if you edit the mockup, re-run
> the conversion rather than hand-editing both.

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
| 3 | Operational | Alerts, cases, agent performance, **p99 latency drift (30d)** |

Every page carries a **country filter** pre-scoped to SE/NO/DK/FI/EE.

> **Operational-page drift tile.** The measure formerly called *Model Drift
> Index* is now **`p99 Latency Drift (30d)`** — it tracks the relative change in
> p99 scoring **latency** versus the most recent data-date at least 30 days
> earlier (it is *not* a statistical model/score-drift metric; the old name was a
> misnomer). It is defined over the weekly `Fact_Latency` seed data, so it renders
> a value on the "p99 Latency Drift & Decline Rate over Time" line and a real
> model-level KPI (rather than a flat 0.00%). The Sentinel alert fires when the
> latency drift exceeds **25%**.

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
