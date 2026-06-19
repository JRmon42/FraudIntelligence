# Heimdall — Infrastructure as Code (Bicep)

Production-grade Azure deployment for the **Heimdall** platform.
All modules follow the naming convention `<svc>-heimdall-<env>-<region>`
(e.g. `kv-heimdall-prod-swc`).

## Topology

| Region | Code | Resource Group | Role |
|---|---|---|---|
| Sweden Central | `swc` | `heimdall_rg` | Primary |
| North Europe   | `neu` | `heimdall_dr_rg` | DR |

Cosmos DB runs **multi-region writes**; Event Hubs uses **geo-DR alias**;
Front Door Premium fronts the scoring API and agentic console.

## Layout

```
infra/
├── main.bicep               # subscription scope: creates RGs, deploys both regions
├── platform.bicep           # resource-group scope: orchestrates per-region modules
├── parameters.prod.json
├── parameters.dev.json
└── modules/
    ├── network.bicep
    ├── loganalytics.bicep
    ├── keyvault.bicep
    ├── acr.bicep
    ├── cosmos.bicep
    ├── eventhubs.bicep
    ├── streamanalytics.bicep
    ├── aml.bicep
    ├── openai.bicep
    ├── containerapps.bicep
    ├── frontdoor.bicep
    ├── fabric.bicep
    ├── synapse.bicep
    ├── purview.bicep
    ├── policy.bicep         # subscription scope
    ├── monitor.bicep
    └── defender.bicep       # subscription scope
```

## Quality bar

Every resource has:

- Tags (`project`, `env`, `costCenter`, `dataClass`, `owner`)
- System-assigned managed identity (where applicable)
- Diagnostic settings → Log Analytics workspace
- TLS 1.2 minimum
- `publicNetworkAccess: Disabled` where supported
- Private endpoint into the `snet-pe` subnet
- RBAC role assignments instead of access keys / connection strings

## Deploy order (handled automatically by `main.bicep`)

1. Subscription-scope: Resource groups, Defender plans, Policy assignments.
2. Per-region (parallel where possible):
   1. Log Analytics + App Insights
   2. VNet + NSGs + Private DNS Zones (primary only; linked from DR via VNet peering — see below)
   3. Key Vault
   4. ACR (primary only, geo-replicated to DR)
   5. Cosmos (primary only, multi-region writes into both)
   6. Event Hubs (both regions, geo-DR alias on primary)
   7. Stream Analytics (primary)
   8. AML, OpenAI (primary)
   9. ACA environment + apps (both regions)
   10. Front Door Premium (primary, global)
   11. Fabric, Synapse, Purview (primary)
   12. Monitor (action group + alerts) (primary)

## Manual / post-deploy steps

These cannot be expressed cleanly in Bicep and must be run **after** the first
successful deployment:

1. **Seed the Key Vault** with required secrets (the parameter file references
   `synapse-sql-admin-password` for prod):
   ```bash
   az keyvault secret set -n synapse-sql-admin-password \
       --vault-name kv-heimdall-prod-swc --value '<strong password>'
   ```
2. **Generate the CMK** in the Key Vault and re-deploy with `cmkKeyUri` set:
   ```bash
   az keyvault key create --vault-name kv-heimdall-prod-swc -n cmk-heimdall \
       --kty RSA --size 3072 --protection software
   ```
   Then re-run `scripts/deploy.sh` so OpenAI and Cosmos pick up the URI.
3. **VNet peering** between `vnet-heimdall-prod-swc` and `vnet-heimdall-prod-neu`,
   plus link the private DNS zones to the DR VNet (the network module currently
   creates DNS zones only in primary — link them from DR after peering).
4. **Purview scans**: register Cosmos / Storage / Synapse / Fabric data sources
   and create scan schedules via Purview REST API or portal — the module
   provisions the account and grants Reader on those sources.
5. **Online endpoint deployment** in AML — push the model image to ACR and
   create a deployment under the `scoring-ep` endpoint placeholder.
6. **Front Door custom domain + cert** if you want a vanity hostname for the
   scoring API and agentic console.
7. **Defender for OpenAI** — confirm the `AI` plan is enabled (preview availability
   varies by subscription).

## Validate

```bash
# build all modules
az bicep build --file infra/main.bicep

# preflight against the subscription
az deployment sub validate \
  --location swedencentral \
  -f infra/main.bicep \
  -p @infra/parameters.prod.json
```

## Deploy

```bash
# 1. Authenticate and pick the subscription
az login && az account set --subscription <YOUR-SUBSCRIPTION-ID>

# 2. Create your parameters file and fill the <PLACEHOLDERS>
cp infra/parameters.example.json infra/parameters.prod.json

# 3. Deploy (runs preflight checks, then a production-readiness report)
./scripts/deploy.sh
```

Everything is variabilised with sensible defaults — override via environment
variables (`SUBSCRIPTION_ID`, `ENV`, `LOCATION`, `PARAM_FILE`,
`SYNAPSE_SQL_ADMIN_PASSWORD`) or the bicep params
(`primaryRegionCode`, `drRegionCode`, `primaryResourceGroupName`,
`drResourceGroupName`). See
[../docs/production-readiness.md](../docs/production-readiness.md) for the full
list of requirements and overridable settings.

> **Secrets:** `synapseSqlAdminPassword` is **never** committed. `deploy.sh`
> reads it from `$SYNAPSE_SQL_ADMIN_PASSWORD` or generates a strong random one
> and stores it in Key Vault as `synapse-sql-admin-password`.
