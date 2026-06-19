#!/usr/bin/env bash
# ============================================================================
# deploy.sh — Idempotent Heimdall platform deployment
#
# Every setting is overridable via environment variables so the script runs
# identically on a laptop and in GitHub Actions. Sensible defaults are applied
# so an existing operator can still just run `./scripts/deploy.sh`.
#
#   ENV / ENVIRONMENT          target env short name      (default: prod)
#   SUBSCRIPTION_ID /
#     AZURE_SUBSCRIPTION_ID    target subscription        (default: current az login)
#   LOCATION / AZURE_LOCATION  primary deployment region  (default: swedencentral)
#   PARAM_FILE                 bicep parameters file      (default: infra/parameters.<env>.json)
#   SYNAPSE_SQL_ADMIN_PASSWORD secret, injected inline    (default: auto-generated)
#   SKIP_PREFLIGHT=1           skip pre-deploy checks
#   SKIP_READINESS=1          skip post-deploy readiness check
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

ENV="${ENV:-${ENVIRONMENT:-prod}}"
LOCATION="${LOCATION:-${AZURE_LOCATION:-swedencentral}}"
PARAM_FILE="${PARAM_FILE:-infra/parameters.${ENV}.json}"
TEMPLATE="infra/main.bicep"
DEPLOYMENT_NAME="heimdall-${ENV}-$(date +%Y%m%d-%H%M%S)"

# Resolve subscription: explicit env wins, else the currently logged-in account.
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-${AZURE_SUBSCRIPTION_ID:-}}"
if [[ -z "$SUBSCRIPTION_ID" ]]; then
  SUBSCRIPTION_ID="$(az account show --query id -o tsv 2>/dev/null || true)"
fi
if [[ -z "$SUBSCRIPTION_ID" ]]; then
  echo "ERROR: no subscription. Run 'az login' or set AZURE_SUBSCRIPTION_ID." >&2
  exit 1
fi

if [[ ! -f "$PARAM_FILE" ]]; then
  echo "ERROR: parameters file '$PARAM_FILE' not found." >&2
  echo "       Copy infra/parameters.example.json to '$PARAM_FILE' and fill it in." >&2
  exit 1
fi

# Synapse SQL admin password is a secret and must never live in a param file.
# Take it from the environment, otherwise generate a strong random one.
SYNAPSE_SQL_ADMIN_PASSWORD="${SYNAPSE_SQL_ADMIN_PASSWORD:-}"
if [[ -z "$SYNAPSE_SQL_ADMIN_PASSWORD" ]]; then
  SYNAPSE_SQL_ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)Aa1!"
  echo "==> Generated a random Synapse SQL admin password (stored in Key Vault below)."
fi

echo "==> Subscription : $SUBSCRIPTION_ID"
echo "==> Environment  : $ENV"
echo "==> Location     : $LOCATION"
echo "==> Parameters   : $PARAM_FILE"
az account set --subscription "$SUBSCRIPTION_ID"

if [[ "${SKIP_PREFLIGHT:-0}" != "1" && -x scripts/preflight.sh ]]; then
  echo "==> Preflight checks"
  PARAM_FILE="$PARAM_FILE" LOCATION="$LOCATION" SUBSCRIPTION_ID="$SUBSCRIPTION_ID" \
    scripts/preflight.sh
fi

echo "==> Bicep build (preflight)"
az bicep build --file "$TEMPLATE"

DEPLOY_PARAMS=(
  --location "$LOCATION"
  --template-file "$TEMPLATE"
  --parameters @"$PARAM_FILE"
  --parameters synapseSqlAdminPassword="$SYNAPSE_SQL_ADMIN_PASSWORD"
  --only-show-errors
)

echo "==> Validating deployment"
az deployment sub validate "${DEPLOY_PARAMS[@]}"

echo "==> What-if (informational only)"
az deployment sub what-if "${DEPLOY_PARAMS[@]}" || true

echo "==> Deploying ($DEPLOYMENT_NAME)"
az deployment sub create --name "$DEPLOYMENT_NAME" "${DEPLOY_PARAMS[@]}"

echo "==> Capturing outputs to .env.deployed"
OUTPUTS=$(az deployment sub show -n "$DEPLOYMENT_NAME" --query properties.outputs -o json)

cat > .env.deployed <<EOF
# Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) from deployment $DEPLOYMENT_NAME
SUBSCRIPTION_ID=$SUBSCRIPTION_ID
ENV=$ENV
PRIMARY_RG=$(echo "$OUTPUTS" | jq -r '.primaryResourceGroup.value')
DR_RG=$(echo "$OUTPUTS" | jq -r '.drResourceGroup.value')
KEY_VAULT_URI=$(echo "$OUTPUTS" | jq -r '.primaryKeyVaultUri.value')
ACR_LOGIN_SERVER=$(echo "$OUTPUTS" | jq -r '.primaryAcrLoginServer.value')
COSMOS_ENDPOINT=$(echo "$OUTPUTS" | jq -r '.primaryCosmosEndpoint.value')
OPENAI_ENDPOINT=$(echo "$OUTPUTS" | jq -r '.primaryOpenAiEndpoint.value')
EVENT_HUBS_NS_PRIMARY=$(echo "$OUTPUTS" | jq -r '.primaryEventHubsNamespace.value')
EVENT_HUBS_NS_DR=$(echo "$OUTPUTS" | jq -r '.drEventHubsNamespace.value')
SCORING_FRONTDOOR_HOST=$(echo "$OUTPUTS" | jq -r '.scoringFrontDoorHost.value')
CONSOLE_FRONTDOOR_HOST=$(echo "$OUTPUTS" | jq -r '.consoleFrontDoorHost.value')
SYNAPSE_SERVERLESS_ENDPOINT=$(echo "$OUTPUTS" | jq -r '.synapseServerlessEndpoint.value')
FABRIC_CAPACITY=$(echo "$OUTPUTS" | jq -r '.fabricCapacityName.value')
PURVIEW_NAME=$(echo "$OUTPUTS" | jq -r '.purviewName.value')
AML_WORKSPACE=$(echo "$OUTPUTS" | jq -r '.amlWorkspaceName.value')
EOF

echo "==> Done. Endpoints:"
cat .env.deployed

# Seed the generated secret into Key Vault so it is never lost.
KV_URI=$(echo "$OUTPUTS" | jq -r '.primaryKeyVaultUri.value')
if [[ -n "$KV_URI" && "$KV_URI" != "null" ]]; then
  KV_NAME=$(echo "$KV_URI" | sed -E 's#https://([^.]+)\..*#\1#')
  echo "==> Storing synapse-sql-admin-password in Key Vault $KV_NAME"
  az keyvault secret set --vault-name "$KV_NAME" \
    --name synapse-sql-admin-password --value "$SYNAPSE_SQL_ADMIN_PASSWORD" \
    --only-show-errors >/dev/null 2>&1 \
    || echo "  (could not write secret — grant yourself 'Key Vault Secrets Officer' and retry)"
fi

if [[ "${SKIP_READINESS:-0}" != "1" && -x scripts/check-readiness.sh ]]; then
  echo
  echo "==> Production-readiness check"
  ENV="$ENV" PRIMARY_RG="$(echo "$OUTPUTS" | jq -r '.primaryResourceGroup.value')" \
    SUBSCRIPTION_ID="$SUBSCRIPTION_ID" scripts/check-readiness.sh || true
fi
