# CI/CD setup

This document lists the GitHub repository configuration required to make the workflows in
`.github/workflows/` pass.

## Required GitHub Actions secrets

| Secret                   | Used by                                 | Description                                                                   |
| ------------------------ | --------------------------------------- | ----------------------------------------------------------------------------- |
| `AZURE_CLIENT_ID`        | bicep-validate, docker-build, infra-deploy, mlops | App Registration (client) ID with OIDC federated credentials. |
| `AZURE_TENANT_ID`        | all azure/login workflows               | Entra tenant ID.                                                              |
| `AZURE_SUBSCRIPTION_ID`  | all azure/login workflows               | Target subscription for deployments.                                          |
| `ACR_NAME`               | docker-build                            | ACR resource name (just the name, not the FQDN).                              |
| `AML_RESOURCE_GROUP`     | mlops                                   | Resource group containing the Azure ML workspace.                             |
| `AML_WORKSPACE`          | mlops                                   | Azure ML workspace name.                                                      |

## Required GitHub Actions variables

| Variable           | Used by         | Description                                              |
| ------------------ | --------------- | -------------------------------------------------------- |
| `AZURE_LOCATION`   | bicep-validate  | Default Azure region for `az deployment sub validate`. Defaults to `swedencentral`. |

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

   # GitHub environments (manual deploys)
   az ad app federated-credential create --id "$APP_OBJ" --parameters '{
     "name": "github-fraudintel-env-prod",
     "issuer": "https://token.actions.githubusercontent.com",
     "subject": "repo:<ORG>/<REPO>:environment:prod",
     "audiences": ["api://AzureADTokenExchange"]
   }'
   ```

3. Grant the SP the minimum required RBAC:

   ```bash
   SP_ID=$APP_ID
   SUB=$(az account show --query id -o tsv)

   # Bicep validate + infra deploy
   az role assignment create --assignee "$SP_ID" --role "Contributor" --scope "/subscriptions/$SUB"

   # ACR push for docker-build
   ACR_ID=$(az acr show -n "$ACR_NAME" --query id -o tsv)
   az role assignment create --assignee "$SP_ID" --role "AcrPush" --scope "$ACR_ID"

   # Azure ML for mlops
   WS_ID=$(az ml workspace show -g "$AML_RG" -n "$AML_WS" --query id -o tsv)
   az role assignment create --assignee "$SP_ID" --role "AzureML Data Scientist" --scope "$WS_ID"
   ```

4. Add the `appId`, `tenantId`, and `subscriptionId` as the GitHub secrets above.

## GitHub environments

Create two environments — `dev` and `prod` — under **Settings → Environments**.

* For `prod`: enable required reviewers and (optionally) restrict deploys to `main`.
* The federated credential subject for `prod` must match `repo:<ORG>/<REPO>:environment:prod`.

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
