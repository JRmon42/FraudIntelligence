# eba-reporter

Quarterly EBA fraud report generator (EBA/GL/2020/01) for the Heimdall platform.

Produces, for each Nordic-Baltic reporting country (SE/NO/DK/FI/EE), three artefacts per quarter:

| File | Audience | Sink |
|---|---|---|
| `eba_<CC>_<YYYY-Qn>.xlsx` | NCA submission portal | ADLS Gen2 `reports/eba/<q>/<cc>/` |
| `eba_<CC>_<YYYY-Qn>.json` | Internal audit trail / API | same |
| `eba_<CC>_<YYYY-Qn>.parquet` | Power BI semantic model | same |

## Run locally

```bash
pip install -e .[dev]
EBA_USE_COSMOS_FALLBACK=true \
EBA_COSMOS_ENDPOINT=https://cosmos-fi-dev.documents.azure.com:443/ \
python -m report --country SE --quarter 2025-Q1 --out ./out --dry-run
```

## Build & deploy

```bash
az acr build -r acrfiprod -t eba-reporter:1.0.0 .
az containerapp job create -n eba-reporter -g rg-fi-prod \
    --environment cae-fi-prod --yaml job.yaml
```

The job runs at **02:00 UTC on the 5th of Jan/Apr/Jul/Oct**, with one replica per
country (parallelism = 5) so all five reports complete in < 5 minutes.

## EBA → source-data field mapping

The aggregates table `gold.eba_report_q` (Fabric Lakehouse) is built by
`fabric/notebooks/30_gold_marts.ipynb` from cleansed silver tables. Below is
the line-of-sight from each EBA Annex field down to the originating source.

### Annex A — Payment volumes & values

| EBA field | Type | Aggregates column | Silver source | Original source |
|---|---|---|---|---|
| Instrument | dim | `instrument` | `silver.transactions.instrument_type` | EFT host PAN BIN range / SEPA scheme code |
| Remote / non-remote | dim | `channel` | `silver.transactions.is_card_present` → mapping | ISO 8583 POS data-code / SEPA local instrument |
| Number of transactions | metric | `tx_count` | `count(*) silver.transactions` | Event Hubs `tx-events` |
| Value of transactions (EUR) | metric | `tx_value_eur` | `sum(amount_eur)` | Event Hubs `tx-events` (FX-converted at booking) |

### Annex B — Fraud breakdown

| EBA field | Aggregates column | Source |
|---|---|---|
| Fraud type | `fraud_type` | `silver.cases.fraud_type` (analyst classification, Cosmos `cases` container) |
| Number of fraudulent transactions | `fraud_count` | join `silver.transactions` ⨯ `silver.cases` on `tx_id` |
| Value of fraudulent transactions (EUR) | `fraud_value_eur` | as above |
| Loss value (EUR) | `loss_value_eur` | `silver.cases.confirmed_loss_eur` |

### Annex C — SCA exemptions

| EBA field | Aggregates column | Source |
|---|---|---|
| SCA applied | `sca_exemption == 'sca_applied'` | `silver.decisions.sca_outcome` (scoring-api decision log, Event Hubs `decisions`) |
| Exemption type used (RTS Art. 10–18) | `sca_exemption` | `silver.decisions.sca_exemption_code` |
| Tx count / value per exemption | `tx_count`, `tx_value_eur` | join with transactions |
| Fraud count / value per exemption | `fraud_count`, `fraud_value_eur` | join with cases |
| Fraud rate (basis points) | `fraud_rate_bps` | derived: `fraud_value_eur / tx_value_eur * 10_000` |

### Annex D — Loss allocation

| EBA field | Aggregates column | Source |
|---|---|---|
| Losses borne by PSP / payer / other | `loss_bearer` | `silver.cases.loss_allocation` (chargeback workflow output) |
| EEA / non-EEA counterparty | `counterparty_geo` | `silver.transactions.merchant_country` mapped to EEA list |
| Loss value | `loss_value_eur` | as Annex B |

### Header fields (cover sheet)

| EBA field | Source |
|---|---|
| Reporting PSP LEI | env var `EBA_PSP_LEI` (KeyVault-backed) |
| Reporting PSP name | env var `EBA_PSP_NAME` |
| Reporting country | CLI `--country` (one replica per country) |
| Reporting period | derived from `--quarter` (start = first day of quarter, end = last day) |
| Submission ID | UUID v4 generated per run |
| Guideline version | constant `EBA/GL/2020/01` |
| Schema version | constant `1.2` |

## Tests

```bash
pytest -q
```

Tests cover:
* round-trip serialisation of `EbaReport`
* aggregation correctness (Annex A–D) on a synthetic fixture
* XLSX shape (sheets, header style)
* CLI invocation with `--dry-run --out`
