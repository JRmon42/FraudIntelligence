#!/usr/bin/env bash
# ============================================================================
# teardown.sh — destroy both resource groups
# ============================================================================
set -euo pipefail

SUBSCRIPTION_ID="ea8d83f8-8538-4914-ae12-24f954d61638"

az account set --subscription "$SUBSCRIPTION_ID"

read -rp "Type 'destroy' to delete BOTH heimdall_rg and heimdall_dr_rg: " confirm
if [[ "$confirm" != "destroy" ]]; then
  echo "Aborted."
  exit 1
fi

echo "==> Deleting heimdall_rg"
az group delete -n heimdall_rg --yes --no-wait

echo "==> Deleting heimdall_dr_rg"
az group delete -n heimdall_dr_rg --yes --no-wait

echo "==> Purging soft-deleted Key Vaults"
for kv in $(az keyvault list-deleted --query "[?contains(name, 'heimdall')].name" -o tsv); do
  az keyvault purge --name "$kv" --no-wait || true
done

echo "==> Purging soft-deleted Cognitive Services (OpenAI)"
for acc in $(az cognitiveservices account list-deleted --query "[?contains(name, 'heimdall')].[name,location]" -o tsv); do
  name=$(echo "$acc" | awk '{print $1}')
  loc=$(echo "$acc" | awk '{print $2}')
  az cognitiveservices account purge --name "$name" --location "$loc" --resource-group heimdall_rg || true
done

echo "==> Teardown initiated (running in background)."
