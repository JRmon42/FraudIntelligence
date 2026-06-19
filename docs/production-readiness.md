# Heimdall — Production-Readiness Requirements

This document defines the **requirements a customer must satisfy to deploy
Heimdall to production**, and how each is verified. The verification is
automated by `scripts/check-readiness.sh`, which runs at the end of every
`scripts/deploy.sh` and prints `PASS` / `WARN` / `FAIL` per requirement,
auto-remediating the safe items and proposing a fix for the rest.

## How to deploy (any customer, 5 steps)

```bash
# 1. Authenticate to the target tenant/subscription
az login
az account set --subscription <YOUR-SUBSCRIPTION-ID>

# 2. Create your parameters file from the template and fill in the <PLACEHOLDERS>
cp infra/parameters.example.json infra/parameters.prod.json
$EDITOR infra/parameters.prod.json

# 3. (Optional) override any variable — all have sensible defaults
export AZURE_LOCATION=swedencentral            # primary region
export SYNAPSE_SQL_ADMIN_PASSWORD='<strong-secret>'   # else auto-generated

# 4. Deploy (runs preflight → bicep → deploy → readiness check)
./scripts/deploy.sh

# 5. Read the readiness report printed at the end and act on any FAIL items
```

Everything is variabilised with defaults, so an existing operator can still
just run `./scripts/deploy.sh`. Overridable settings:

| Variable | Default | Used by |
|---|---|---|
| `SUBSCRIPTION_ID` / `AZURE_SUBSCRIPTION_ID` | current `az` login | deploy, teardown, scale |
| `ENV` / `ENVIRONMENT` | `prod` | deploy (selects `parameters.<env>.json`) |
| `LOCATION` / `AZURE_LOCATION` | `swedencentral` | deploy |
| `PARAM_FILE` | `infra/parameters.<env>.json` | deploy |
| `SYNAPSE_SQL_ADMIN_PASSWORD` | auto-generated | deploy (injected, never committed) |
| `primaryRegionCode` / `drRegionCode` (bicep) | `swc` / `neu` | main.bicep |
| `primaryResourceGroupName` / `drResourceGroupName` (bicep) | `heimdall_rg` / `heimdall_dr_rg` | main.bicep |
| `PRIMARY_RG` / `DR_RG` | `heimdall_rg` / `heimdall_dr_rg` | teardown, scale |

## Prerequisites (checked by `scripts/preflight.sh`)

- Azure CLI ≥ 2.50 logged in (`az login`), plus `jq` and `openssl`.
- Owner or Contributor + User Access Administrator on the target subscription
  (needed for RBAC role assignments and policy/Defender at subscription scope).
- The parameters file exists, has no `<PLACEHOLDER>` values, and contains **no**
  plaintext `synapseSqlAdminPassword`.
- Required resource providers registered (auto-registered by preflight):
  `Microsoft.App`, `Microsoft.ContainerRegistry`, `Microsoft.DocumentDB`,
  `Microsoft.EventHub`, `Microsoft.KeyVault`, `Microsoft.CognitiveServices`,
  `Microsoft.MachineLearningServices`, `Microsoft.OperationalInsights`,
  `Microsoft.Insights`, `Microsoft.Network`, `Microsoft.Cdn`,
  `Microsoft.Fabric`, `Microsoft.Synapse`, `Microsoft.Purview`,
  `Microsoft.Security`.
- Sufficient regional quota (Container Apps vCPU, OpenAI TPM, Cosmos RU).

## Requirements (verified by `scripts/check-readiness.sh`)

| ID | Requirement | Verification | Auto-fix |
|---|---|---|---|
| **R1** | Workloads authenticate with **managed identity**, not keys | every Container App has `identity.type != None` | propose |
| **R2** | **Key Vault** has soft-delete **and** purge protection | `properties.enableSoftDelete` & `enablePurgeProtection` | propose |
| **R3** | **ACR** is not publicly reachable | `publicNetworkAccess == Disabled` | propose |
| **R4** | **Observability**: Log Analytics + Application Insights exist | resource counts in RG | propose |
| **R5a** | **Cost guardrails**: scale-to-min / scale-to-prod present | files executable | `chmod +x` |
| **R5b** | A **subscription budget** is configured | `az consumption budget list` | propose |
| **R6** | **Resilience**: Cosmos has a backup policy | `backupPolicy.type` | n/a |
| **R7** | **Microsoft Defender for Cloud** plans on Standard | `az security pricing list` | propose (cost) |
| **R8** | Resource group carries `project`/`env`/`owner` **tags** | `az group show` tags | **auto-applies tags** |
| **R9** | Required **CI/CD workflows** present (`ci`, `infra-deploy`, `docker-build`, `scale`) | files exist | propose |
| **R10** | **No plaintext secrets** committed (`synapseSqlAdminPassword`) | grep `infra/` | propose |
| **R11** | **Compliance**: Azure Policy assignments active (data residency / TLS / tags) | `az policy assignment list` | propose |

`WARN` = resource not present yet or optional hardening; `FAIL` = a required
control is missing. The checker only auto-applies **non-destructive, low-cost**
remediations (R5a `chmod`, R8 tags, provider registration in preflight); it
*proposes* — and never silently applies — anything that costs money, changes
network exposure, or is irreversible.

## Accepted tradeoffs

- **R3 / ACR public access.** The container registry is Premium with a private
  endpoint (the secure target is `publicNetworkAccess: Disabled`). It is left
  **Enabled** so the `docker-build` workflow can push images from
  GitHub-hosted (public) runners. To reach full lockdown, run the image build
  on a **self-hosted runner inside the VNet** (or via an ACR task), then
  `az acr update -n <acr> --public-network-enabled false`. The readiness check
  reports this as `WARN`, not `FAIL`, when a private endpoint already exists.

## Post-deploy manual steps

See [infra/README.md](../infra/README.md#manual--post-deploy-steps) for the
items that cannot be expressed in Bicep (CMK generation, VNet peering, Purview
scan registration, AML online endpoint, Front Door custom domain).
