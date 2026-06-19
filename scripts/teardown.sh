#!/usr/bin/env bash
# ============================================================================
# teardown.sh — destroy both resource groups
#
# Overridable via env vars (defaults match the reference deployment):
#   SUBSCRIPTION_ID / AZURE_SUBSCRIPTION_ID  (default: current az login)
#   PRIMARY_RG  (default: heimdall_rg)
#   DR_RG       (default: heimdall_dr_rg)
#   FORCE=1     skip the interactive confirmation (for CI)
# ============================================================================
set -euo pipefail

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-${AZURE_SUBSCRIPTION_ID:-}}"
if [[ -z "$SUBSCRIPTION_ID" ]]; then
  SUBSCRIPTION_ID="$(az account show --query id -o tsv 2>/dev/null || true)"
fi
PRIMARY_RG="${PRIMARY_RG:-heimdall_rg}"
DR_RG="${DR_RG:-heimdall_dr_rg}"

[[ -n "$SUBSCRIPTION_ID" ]] && az account set --subscription "$SUBSCRIPTION_ID"

if [[ "${FORCE:-0}" != "1" ]]; then
  read -rp "Type 'destroy' to delete BOTH $PRIMARY_RG and $DR_RG: " confirm
  if [[ "$confirm" != "destroy" ]]; then
    echo "Aborted."
    exit 1
  fi
fi

echo "==> Deleting $PRIMARY_RG"
az group delete -n "$PRIMARY_RG" --yes --no-wait || true

echo "==> Deleting $DR_RG"
az group delete -n "$DR_RG" --yes --no-wait || true

echo "==> Purging soft-deleted Key Vaults"
for kv in $(az keyvault list-deleted --query "[?contains(name, 'heimdall')].name" -o tsv); do
  az keyvault purge --name "$kv" --no-wait || true
done

echo "==> Purging soft-deleted Cognitive Services (OpenAI)"
for acc in $(az cognitiveservices account list-deleted --query "[?contains(name, 'heimdall')].[name,location]" -o tsv); do
  name=$(echo "$acc" | awk '{print $1}')
  loc=$(echo "$acc" | awk '{print $2}')
  az cognitiveservices account purge --name "$name" --location "$loc" --resource-group "$PRIMARY_RG" || true
done

echo "==> Teardown initiated (running in background)."
