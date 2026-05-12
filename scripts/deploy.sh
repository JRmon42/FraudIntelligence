#!/usr/bin/env bash
# ============================================================================
# deploy.sh — Idempotent FraudIntelligence platform deployment
# ============================================================================
set -euo pipefail

SUBSCRIPTION_ID="ea8d83f8-8538-4914-ae12-24f954d61638"
LOCATION="swedencentral"
PARAM_FILE="${PARAM_FILE:-infra/parameters.prod.json}"
TEMPLATE="infra/main.bicep"
DEPLOYMENT_NAME="fraudintel-$(date +%Y%m%d-%H%M%S)"

cd "$(dirname "$0")/.."

echo "==> Setting subscription: $SUBSCRIPTION_ID"
az account set --subscription "$SUBSCRIPTION_ID"

echo "==> Bicep build (preflight)"
az bicep build --file "$TEMPLATE"

echo "==> Validating deployment"
az deployment sub validate \
  --location "$LOCATION" \
  --template-file "$TEMPLATE" \
  --parameters @"$PARAM_FILE" \
  --only-show-errors

echo "==> What-if (informational only)"
az deployment sub what-if \
  --location "$LOCATION" \
  --template-file "$TEMPLATE" \
  --parameters @"$PARAM_FILE" \
  --only-show-errors || true

echo "==> Deploying ($DEPLOYMENT_NAME)"
az deployment sub create \
  --name "$DEPLOYMENT_NAME" \
  --location "$LOCATION" \
  --template-file "$TEMPLATE" \
  --parameters @"$PARAM_FILE" \
  --only-show-errors

echo "==> Capturing outputs to .env.deployed"
OUTPUTS=$(az deployment sub show -n "$DEPLOYMENT_NAME" --query properties.outputs -o json)

cat > .env.deployed <<EOF
# Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) from deployment $DEPLOYMENT_NAME
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
