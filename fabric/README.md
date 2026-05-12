# Microsoft Fabric — FraudIntelligence Medallion

OneLake-backed Lakehouse `lh_fraud` in workspace `ws-fi-prod`, organised as:

```
bronze   raw Avro from Event Hubs Capture (append-only, partitioned by ingest_date)
silver   cleansed, deduped, EUR-converted, PII-tokenised via Purview
gold     curated marts for Power BI + EBA reporter
```

## Notebooks

| Notebook | Cadence | Output |
|---|---|---|
| `00_setup_lakehouse.ipynb` | once | schemas + Delta tables |
| `10_bronze_ingest.ipynb` | hourly | `bronze.transactions / decisions / cases` |
| `20_silver_clean.ipynb` | hourly | `silver.transactions / decisions / cases` |
| `30_gold_marts.ipynb` | daily 02:00 UTC | `gold.fraud_kpis_daily`, `gold.eba_report_q`, `gold.psd2_exemption_mix`, `gold.scoring_latency_p99` |

## One-time setup

1. Create the workspace `ws-fi-prod` and Lakehouse `lh_fraud` in the Fabric portal
   (sovereign capacity in Sweden Central).
2. Import all four notebooks (`Workspace > New > Notebook > Import`).
3. Attach each notebook to `lh_fraud` (`Add data items` panel).
4. Run `00_setup_lakehouse.ipynb` once — creates schemas, tables, and reference
   tables (`ref.fx_daily`, `ref.bin_country`).
5. Grant the workspace identity the following role assignments:
   * `Storage Blob Data Reader` on `fiprodcap` (Event Hubs Capture account)
   * `Storage Blob Data Contributor` on `fiprodlh` (Lakehouse account)
   * `Purview Tokenisation User` on `pv-fi-prod`
6. Import `pipelines/orchestrate_medallion.json` via Data Factory in Fabric and
   replace the four globalParameters with the IDs of your imported notebooks.
   The pipeline ships with an hourly schedule; the gold step is idempotent so
   running it every hour is safe — only the latest `process_date` is rewritten.

## Run

```bash
# from the Fabric REST API or az fabric CLI
az fabric pipeline run --workspace ws-fi-prod --pipeline orchestrate_medallion
```

## Re-processing a day

Set `pipeline.process_date` and `pipeline.quarter` parameters when invoking the
pipeline manually:

```json
{ "pipeline.process_date": "2025-01-14", "pipeline.quarter": "2025-Q1" }
```

The silver/gold notebooks use Delta `replaceWhere` so a re-run cleanly
overwrites the affected partitions only.

## Lineage / governance

* All silver tables register their schema with **Microsoft Purview** via the
  `lh_fraud` collection.
* PAN tokens are written using Purview-managed FPE keys — re-keying is a single
  Purview API call and triggers a silver backfill.
* Sensitive columns (`pan_token`, `merchant_id`) are labelled `Confidential —
  Payments PII` and inherit row-level security in the Power BI semantic model.
