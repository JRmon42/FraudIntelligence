# Grafana dashboards

Dashboard models for the **Azure Managed Grafana** instance
(`graf-heimdall-prod-swc`, deployed by `infra/modules/grafana.bicep`).

> Azure Managed Grafana dashboards are **not** ARM resources, so they cannot be
> declared in Bicep. They are version-controlled here and pushed via the import
> script after the infrastructure is deployed.

## scoring-api-slo.json — "Heimdall — Scoring API SLO"

UID `heimdall-scoring-slo`. Panels (all via the built-in **Azure Monitor** data
source, `uid: azure-monitor-oob`):

| Panel | Source | Query |
|-------|--------|-------|
| Scoring API latency p99/p95 (SLO < 18 ms) | App Insights (Logs/KQL) | `requests` percentile of `duration` |
| Scoring replicas (auto scale-out) | Azure Monitor metric | `microsoft.app/containerapps` → `Replicas` |
| Throughput — scoring requests/min | App Insights (Logs/KQL) | `requests` count per bin |
| Decision mix (APPROVE/SCA/DECLINE) | App Insights (Logs/KQL) | `customDimensions["decision"]` |
| Degraded decisions (fail-open) | App Insights (Logs/KQL) | `customDimensions["degraded"]` |
| Cosmos DB normalized RU & total RU | Azure Monitor metric | `microsoft.documentdb/databaseaccounts` |

The JSON uses `${PLACEHOLDER}` tokens (subscription, resource group, App
Insights resource ID, scoring app name, Cosmos account name, datasource UID)
that the import script substitutes at push time, so the same model works across
environments. Grafana macros such as `$__timeInterval` are preserved.

## Importing

```bash
# Uses az login + Grafana Admin/Editor role on the instance.
./scripts/import-grafana-dashboard.sh
```

Override targets via env vars (`GRAFANA_NAME`, `RESOURCE_GROUP`,
`SUBSCRIPTION_ID`, `APPINSIGHTS_RESOURCE_ID`, `SCORING_APP_NAME`,
`COSMOS_ACCOUNT_NAME`, `GRAFANA_AZ_MONITOR_DS_UID`, `DASHBOARD_FILE`).
