#!/usr/bin/env bash
# ============================================================================
# teardown.sh — destroy both resource groups
# ============================================================================
set -euo pipefail

SUBSCRIPTION_ID="ea8d83f8-8538-4914-ae12-24f954d61638"

az account set --subscription "$SUBSCRIPTION_ID"

read -rp "Type 'destroy' to delete BOTH fraudintelligence_rg and fraudintelligence_dr_rg: " confirm
if [[ "$confirm" != "destroy" ]]; then
  echo "Aborted."
  exit 1
fi

echo "==> Deleting fraudintelligence_rg"
az group delete -n fraudintelligence_rg --yes --no-wait

echo "==> Deleting fraudintelligence_dr_rg"
az group delete -n fraudintelligence_dr_rg --yes --no-wait

echo "==> Purging soft-deleted Key Vaults"
for kv in $(az keyvault list-deleted --query "[?contains(name, 'fraudintel')].name" -o tsv); do
  az keyvault purge --name "$kv" --no-wait || true
done

echo "==> Purging soft-deleted Cognitive Services (OpenAI)"
for acc in $(az cognitiveservices account list-deleted --query "[?contains(name, 'fraudintel')].[name,location]" -o tsv); do
  name=$(echo "$acc" | awk '{print $1}')
  loc=$(echo "$acc" | awk '{print $2}')
  az cognitiveservices account purge --name "$name" --location "$loc" --resource-group fraudintelligence_rg || true
done

echo "==> Teardown initiated (running in background)."
