#!/usr/bin/env bash
# ============================================================================
# preflight.sh — pre-deploy gate. Verifies the prerequisites that must be true
# BEFORE a deployment can succeed, and auto-remediates the safe ones (resource
# provider registration, CLI extension config). Exits non-zero on a hard stop.
#
#   PARAM_FILE       parameters file to validate (default: infra/parameters.prod.json)
#   LOCATION         intended region            (default: swedencentral)
#   SUBSCRIPTION_ID  target subscription        (default: current az login)
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."

PARAM_FILE="${PARAM_FILE:-infra/parameters.prod.json}"
LOCATION="${LOCATION:-swedencentral}"

fail=0
ok()   { printf '  \033[0;32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[0;33m!\033[0m %s\n' "$1"; }
bad()  { printf '  \033[0;31m✗\033[0m %s\n' "$1"; fail=1; }

# --- Tooling -----------------------------------------------------------------
for t in az jq openssl; do
  command -v "$t" >/dev/null 2>&1 && ok "$t present" || bad "$t not installed"
done

# --- Auth --------------------------------------------------------------------
if az account show >/dev/null 2>&1; then
  ok "Azure CLI is logged in ($(az account show --query name -o tsv 2>/dev/null))"
else
  bad "Azure CLI not logged in — run 'az login'"
fi

# --- Parameters file ---------------------------------------------------------
if [[ -f "$PARAM_FILE" ]]; then
  ok "Parameters file present: $PARAM_FILE"
  if grep -q '<[A-Z-]*>' "$PARAM_FILE"; then
    bad "Parameters file still contains <PLACEHOLDER> values — fill them in"
  else
    ok "No <PLACEHOLDER> values left in parameters file"
  fi
  if grep -Eiq '"synapseSqlAdminPassword"' "$PARAM_FILE"; then
    bad "synapseSqlAdminPassword must NOT be committed — remove it (deploy.sh injects it)"
  else
    ok "No plaintext synapseSqlAdminPassword in parameters file"
  fi
else
  bad "Parameters file '$PARAM_FILE' not found (copy infra/parameters.example.json)"
fi

# --- Region validity ---------------------------------------------------------
if az account list-locations --query "[?name=='$LOCATION'].name" -o tsv 2>/dev/null | grep -q .; then
  ok "Region '$LOCATION' is valid for this subscription"
else
  warn "Could not confirm region '$LOCATION' (offline or restricted)"
fi

# --- Resource providers (auto-register) -------------------------------------
providers=(
  Microsoft.App Microsoft.ContainerRegistry Microsoft.DocumentDB
  Microsoft.EventHub Microsoft.KeyVault Microsoft.CognitiveServices
  Microsoft.MachineLearningServices Microsoft.OperationalInsights
  Microsoft.Insights Microsoft.Network Microsoft.Cdn Microsoft.Fabric
  Microsoft.Synapse Microsoft.Purview Microsoft.Security
)
echo "  Checking resource providers (auto-registering unregistered ones)…"
for p in "${providers[@]}"; do
  state=$(az provider show -n "$p" --query registrationState -o tsv 2>/dev/null || echo Unknown)
  if [[ "$state" == "Registered" ]]; then
    :
  else
    warn "$p is '$state' — registering…"
    az provider register -n "$p" --only-show-errors >/dev/null 2>&1 \
      && ok "$p registration requested" \
      || warn "$p could not be registered (insufficient rights?)"
  fi
done
ok "Resource provider check complete"

# --- CLI extensions ----------------------------------------------------------
az config set extension.use_dynamic_install=yes_without_prompt >/dev/null 2>&1 \
  && ok "Azure CLI dynamic extension install enabled" \
  || warn "Could not set extension.use_dynamic_install"

echo
if [[ "$fail" -ne 0 ]]; then
  echo "Preflight FAILED — fix the ✗ items above before deploying." >&2
  exit 1
fi
echo "Preflight passed."
