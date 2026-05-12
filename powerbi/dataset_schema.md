# Dataset schema — `EBA Fraud Semantic Model`

Star schema published to the Fabric workspace `ws-fi-prod`. All facts are in
**Direct Lake** mode pointing at Delta tables in the `lh_fraud` Lakehouse;
all dimensions are **imported** (small, slowly changing).

Legend — Mode: `DL` = Direct Lake, `IMP` = imported.

---

## Dimensions

### `Dim_Country` (IMP)

| Column | Type | Source |
|---|---|---|
| CountryCode | string (PK) | hard-coded list (SE/NO/DK/FI/EE) |
| CountryName | string | hard-coded |
| Region | string | hard-coded (Nordics / Baltics) |

### `Dim_Date` (IMP)

| Column | Type | Source |
|---|---|---|
| Date | datetime (PK, marked as Date table) | M expression `List.Dates(2023-01-01 → 2027-12-31)` |
| Year | int64 | derived |
| Quarter | string `YYYY-Qn` | derived |
| Month | int64 | derived |
| MonthName | string | derived |

### `Dim_Instrument` (IMP)

| Column | Type | Source |
|---|---|---|
| Instrument | string (PK) | constant list — matches `gold.eba_report_q.instrument` |
| InstrumentLabel | string | display label |

### `Dim_Exemption` (IMP)

| Column | Type | Source |
|---|---|---|
| ExemptionCode | string (PK) | matches `gold.eba_report_q.sca_exemption` |
| ExemptionLabel | string | display label |
| RtsArticle | string | RTS reference (Art. 11–18) |

### `Dim_FraudType` (IMP)

| Column | Type | Source |
|---|---|---|
| FraudTypeCode | string (PK) | matches `gold.eba_report_q.fraud_type` |
| FraudTypeLabel | string | display label |

---

## Facts

### `Fact_Tx` (DL → `lh_fraud.gold.fraud_kpis_daily`)

| Column | Type | Aggregation | Source column |
|---|---|---|---|
| BookingDate | datetime | none | `kpi_date` |
| CountryCode | string | none | `issuer_country` |
| Instrument | string | none | `instrument_type` |
| TxCount | int64 | sum | `tx_count` |
| TxValueEur | decimal (€#,0.00) | sum | `tx_value_eur` |
| DeclineCount | int64 | sum | `decline_count` |
| FraudCount | int64 | sum | `fraud_count` |
| FraudValueEur | decimal (€#,0.00) | sum | `fraud_value_eur` |
| LossValueEur | decimal (€#,0.00) | sum | `loss_value_eur` |

### `Fact_Eba` (DL → `lh_fraud.gold.eba_report_q`)

| Column | Type | Aggregation | Source column |
|---|---|---|---|
| Quarter | string | none | `quarter` |
| CountryCode | string | none | `reporting_country` |
| Instrument | string | none | `instrument` |
| Channel | string | none | `channel` |
| ExemptionCode | string | none | `sca_exemption` |
| FraudTypeCode | string | none | `fraud_type` |
| CounterpartyGeo | string | none | `counterparty_geo` |
| LossBearer | string | none | `loss_bearer` |
| TxCount | int64 | sum | `tx_count` |
| TxValueEur | decimal | sum | `tx_value_eur` |
| FraudCount | int64 | sum | `fraud_count` |
| FraudValueEur | decimal | sum | `fraud_value_eur` |
| LossValueEur | decimal | sum | `loss_value_eur` |

### `Fact_Exemption` (DL → `lh_fraud.gold.psd2_exemption_mix`)

| Column | Type | Aggregation | Source column |
|---|---|---|---|
| KpiDate | datetime | none | `kpi_date` |
| CountryCode | string | none | `issuer_country` |
| ExemptionCode | string | none | `sca_exemption_code` |
| TxCount | int64 | sum | `tx_count` |
| TxValueEur | decimal | sum | `tx_value_eur` |
| FraudCount | int64 | sum | `fraud_count` |
| FraudRateBps | double | average | `fraud_rate_bps` |

### `Fact_Latency` (DL → `lh_fraud.gold.scoring_latency_p99`)

| Column | Type | Aggregation | Source column |
|---|---|---|---|
| KpiDate | datetime | none | `kpi_date` |
| ModelVersion | string | none | `model_version` |
| P50Ms | double | average | `p50_ms` |
| P95Ms | double | average | `p95_ms` |
| P99Ms | double | average | `p99_ms` |
| SampleCount | int64 | sum | `sample_count` |

---

## Relationships (all single-direction, *-1 from fact to dim)

| From (M side) | → | To (1 side) |
|---|---|---|
| `Fact_Tx[CountryCode]` | → | `Dim_Country[CountryCode]` |
| `Fact_Tx[BookingDate]` | → | `Dim_Date[Date]` |
| `Fact_Tx[Instrument]` | → | `Dim_Instrument[Instrument]` |
| `Fact_Eba[CountryCode]` | → | `Dim_Country[CountryCode]` |
| `Fact_Eba[Instrument]` | → | `Dim_Instrument[Instrument]` |
| `Fact_Eba[ExemptionCode]` | → | `Dim_Exemption[ExemptionCode]` |
| `Fact_Eba[FraudTypeCode]` | → | `Dim_FraudType[FraudTypeCode]` |
| `Fact_Exemption[KpiDate]` | → | `Dim_Date[Date]` |
| `Fact_Exemption[CountryCode]` | → | `Dim_Country[CountryCode]` |
| `Fact_Exemption[ExemptionCode]` | → | `Dim_Exemption[ExemptionCode]` |
| `Fact_Latency[KpiDate]` | → | `Dim_Date[Date]` |

---

## Sensitivity labels

* `Fact_Tx`, `Fact_Eba` — **Confidential — Payments PII** (inherited via Purview)
* All dimensions — **General**
