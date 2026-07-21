# CI/CD setup

This document lists the GitHub repository configuration required to make the workflows in
`.github/workflows/` pass.

## Required GitHub Actions secrets

Seven secrets are required in total (**Settings → Secrets and variables → Actions → Secrets**):

| Secret                        | Used by                                             | Description                                                                   |
| ----------------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------- |
| `AZURE_CLIENT_ID`             | bicep-validate, docker-build, infra-deploy, mlops, scale | App Registration (client) ID with OIDC federated credentials.            |
| `AZURE_TENANT_ID`             | all azure/login workflows                           | Entra tenant ID.                                                              |
| `AZURE_SUBSCRIPTION_ID`       | all azure/login workflows                           | Target subscription for deployments.                                          |
| `ACR_NAME`                    | docker-build                                        | ACR resource name (just the name, not the FQDN).                              |
| `AML_RESOURCE_GROUP`          | mlops                                               | Resource group containing the Azure ML workspace.                             |
| `AML_WORKSPACE`               | mlops                                               | Azure ML workspace name.                                                      |
| `SYNAPSE_SQL_ADMIN_PASSWORD`  | infra-deploy, bicep-validate                        | Synapse SQL admin password (`main.bicep` requires it even though Synapse is AAD-first). Generate a strong value; `scripts/deploy.sh` auto-generates + stores one in Key Vault if this is empty, but CI needs it set. |

## Required GitHub Actions variables

Set under **Settings → Secrets and variables → Actions → Variables** (these are non-secret):

| Variable                      | Used by         | Description                                              |
| ----------------------------- | --------------- | -------------------------------------------------------- |
| `AZURE_LOCATION`              | bicep-validate  | Default Azure region for `az deployment sub validate`. Defaults to `swedencentral`. |
| `SYNAPSE_AAD_ADMIN_LOGIN`     | bicep-validate  | Synapse AAD admin UPN (e.g. `admin@yourtenant.onmicrosoft.com`). Required so `az deployment sub validate` can bind the `synapseAadAdminLogin` parameter. |
| `SYNAPSE_AAD_ADMIN_OBJECT_ID` | bicep-validate  | Object ID (GUID) of the Synapse AAD admin — binds `synapseAadAdminObjectId`. |

> **Note — `infra-deploy` vs `bicep-validate` parameters.** `infra-deploy` runs `scripts/deploy.sh`,
> which reads `infra/parameters.<env>.json` (that file already holds `synapseAadAdminLogin` /
> `synapseAadAdminObjectId`) and injects `synapseSqlAdminPassword` from the secret. `bicep-validate`
> does **not** use a parameter file, so it reads those two AAD values from the repo variables above.
> Copy `infra/parameters.example.json` to `infra/parameters.<env>.json` and fill every `<PLACEHOLDER>`
> before running `infra-deploy`.

## OIDC federated credentials

The pipelines authenticate to Azure using GitHub OIDC — **no client secret is stored**.

### One-time setup (per environment)

1. Create the App Registration:

   ```bash
   az ad app create --display-name "github-fraudintel-oidc"
   APP_ID=$(az ad app list --display-name "github-fraudintel-oidc" --query '[0].appId' -o tsv)
   APP_OBJ=$(az ad app list --display-name "github-fraudintel-oidc" --query '[0].id' -o tsv)
   az ad sp create --id "$APP_ID"
   ```

2. Add federated credentials for each ref pattern you need:

   ```bash
   # main branch (push pipelines)
   az ad app federated-credential create --id "$APP_OBJ" --parameters '{
     "name": "github-fraudintel-main",
     "issuer": "https://token.actions.githubusercontent.com",
     "subject": "repo:<ORG>/<REPO>:ref:refs/heads/main",
     "audiences": ["api://AzureADTokenExchange"]
   }'

   # pull requests (validation pipelines)
   az ad app federated-credential create --id "$APP_OBJ" --parameters '{
     "name": "github-fraudintel-pr",
     "issuer": "https://token.actions.githubusercontent.com",
     "subject": "repo:<ORG>/<REPO>:pull_request",
     "audiences": ["api://AzureADTokenExchange"]
   }'

   # GitHub environments (manual deploys: infra-deploy + scale bind to `environment:`)
   # Add BOTH prod and dev — the OIDC subject is repo:<ORG>/<REPO>:environment:<env>,
   # NOT a branch/ref subject, so the ref/pull_request FICs above do NOT cover them.
   for E in prod dev; do
     az ad app federated-credential create --id "$APP_OBJ" --parameters "{
       \"name\": \"github-fraudintel-env-$E\",
       \"issuer\": \"https://token.actions.githubusercontent.com\",
       \"subject\": \"repo:<ORG>/<REPO>:environment:$E\",
       \"audiences\": [\"api://AzureADTokenExchange\"]
     }"
   done
   ```

   You should end up with **four** federated credentials: `ref:refs/heads/main`,
   `pull_request`, `environment:prod`, and `environment:dev`. A missing environment
   credential fails `azure/login` with `AADSTS700213: No matching federated identity record`.

3. Grant the SP the required RBAC. **`Contributor` alone is not enough** — `main.bicep`
   creates role assignments and subscription-scope policy assignments, both of which
   `Contributor` explicitly excludes (`Microsoft.Authorization/*/write`):

   ```bash
   SP_ID=$APP_ID
   SUB=$(az account show --query id -o tsv)

   # Deploy resources (infra-deploy, scale, bicep-validate)
   az role assignment create --assignee "$SP_ID" --role "Contributor" --scope "/subscriptions/$SUB"

   # Create the ~11 roleAssignments in main.bicep (managed-identity RBAC)
   az role assignment create --assignee "$SP_ID" \
     --role "Role Based Access Control Administrator" --scope "/subscriptions/$SUB"

   # Create the 5 subscription-scope policyAssignments in main.bicep
   az role assignment create --assignee "$SP_ID" \
     --role "Resource Policy Contributor" --scope "/subscriptions/$SUB"

   # ACR push for docker-build
   ACR_ID=$(az acr show -n "$ACR_NAME" --query id -o tsv)
   az role assignment create --assignee "$SP_ID" --role "AcrPush" --scope "$ACR_ID"

   # Azure ML for mlops
   WS_ID=$(az ml workspace show -g "$AML_RG" -n "$AML_WS" --query id -o tsv)
   az role assignment create --assignee "$SP_ID" --role "AzureML Data Scientist" --scope "$WS_ID"
   ```

   > Without `Role Based Access Control Administrator`, deploys fail on
   > `Microsoft.Authorization/roleAssignments/write`; without `Resource Policy Contributor`
   > they fail on `Microsoft.Authorization/policyAssignments/write` (e.g. `heimdall-allowed-locations`).

4. Add the `appId`, `tenantId`, and `subscriptionId` as the GitHub secrets above.

## GitHub environments

Create two environments — `dev` and `prod` — under **Settings → Environments**.

* For `prod`: enable required reviewers and (optionally) restrict deploys to `main`.
* The federated credential subject must match `repo:<ORG>/<REPO>:environment:<env>` for **both**
  `prod` and `dev` (see the OIDC step above) — `infra-deploy` and `scale` accept either environment
  as a `workflow_dispatch` input.

## Branch protection

Recommended for `main`:

* Require status checks: `ci / python (transaction-simulator (py3.11))` (and the other matrix legs).
* Require linear history.
* Disallow force-push.

## Local validation

```bash
# Lint workflows
brew install actionlint && actionlint

# Lint compose
docker compose config -q

# Lint bicep
az bicep build --file infra/main.bicep
```
