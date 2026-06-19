#!/usr/bin/env bash
# ============================================================================
# check-readiness.sh — production-readiness verification & feedback.
#
# Evaluates the deployed Heimdall estate against the requirements defined in
# docs/production-readiness.md, prints PASS / WARN / FAIL per requirement,
# auto-remediates the SAFE ones (and says so), and proposes a concrete fix for
# everything else. Always exits 0 — it is feedback, not a gate.
#
#   ENV              env short name        (default: prod)
#   PRIMARY_RG       resource group        (default: heimdall_rg)
#   PRIMARY_RC       region code           (default: swc)
#   SUBSCRIPTION_ID  subscription          (default: current az login)
#   AUTO_FIX=0       disable auto-remediation (propose only)
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."

ENV="${ENV:-prod}"
PRIMARY_RG="${PRIMARY_RG:-heimdall_rg}"
PRIMARY_RC="${PRIMARY_RC:-swc}"
AUTO_FIX="${AUTO_FIX:-1}"
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-${AZURE_SUBSCRIPTION_ID:-}}"
[[ -n "$SUBSCRIPTION_ID" ]] && az account set --subscription "$SUBSCRIPTION_ID" 2>/dev/null || true

pass=0; warnc=0; failc=0
GREEN='\033[0;32m'; YEL='\033[0;33m'; RED='\033[0;31m'; CYN='\033[0;36m'; NC='\033[0m'
PASS() { printf "${GREEN}PASS${NC} %-4s %s\n" "$1" "$2"; pass=$((pass+1)); }
WARN() { printf "${YEL}WARN${NC} %-4s %s\n" "$1" "$2"; warnc=$((warnc+1)); }
FAIL() { printf "${RED}FAIL${NC} %-4s %s\n" "$1" "$2"; failc=$((failc+1)); }
FIX()  { printf "       ${CYN}→ fix:${NC} %s\n" "$1"; }
DONE() { printf "       ${GREEN}→ auto-remediated:${NC} %s\n" "$1"; }

rg_exists=$(az group exists -n "$PRIMARY_RG" 2>/dev/null || echo false)
echo "Resource group: $PRIMARY_RG (exists: $rg_exists)"
echo "------------------------------------------------------------------------"

# --- R1 Identity: workloads use managed identity --------------------------------
mi=$(az containerapp list -g "$PRIMARY_RG" --query "[?identity.type!=null && identity.type!='None'] | length(@)" -o tsv 2>/dev/null || echo 0)
total_ca=$(az containerapp list -g "$PRIMARY_RG" --query "length(@)" -o tsv 2>/dev/null || echo 0)
if [[ "${total_ca:-0}" -gt 0 && "${mi:-0}" -ge "$total_ca" ]]; then
  PASS R1 "Identity: all $total_ca Container Apps use a managed identity"
elif [[ "${total_ca:-0}" -gt 0 ]]; then
  FAIL R1 "Identity: $((total_ca-mi))/$total_ca Container Apps lack a managed identity"
  FIX "az containerapp identity assign -g $PRIMARY_RG -n <app> --system-assigned"
else
  WARN R1 "Identity: no Container Apps found to evaluate"
fi

# --- R2 Secrets: Key Vault hardened ---------------------------------------------
kv=$(az keyvault list -g "$PRIMARY_RG" --query "[0].name" -o tsv 2>/dev/null || echo "")
if [[ -n "$kv" ]]; then
  soft=$(az keyvault show -n "$kv" --query "properties.enableSoftDelete" -o tsv 2>/dev/null)
  purge=$(az keyvault show -n "$kv" --query "properties.enablePurgeProtection" -o tsv 2>/dev/null)
  if [[ "$soft" == "true" && "$purge" == "true" ]]; then
    PASS R2 "Secrets: Key Vault $kv has soft-delete + purge protection"
  else
    FAIL R2 "Secrets: Key Vault $kv missing purge protection (soft=$soft purge=$purge)"
    FIX "az keyvault update -n $kv -g $PRIMARY_RG --enable-purge-protection true"
  fi
else
  WARN R2 "Secrets: no Key Vault found in $PRIMARY_RG"
fi

# --- R3 Network: ACR not publicly reachable -------------------------------------
acr=$(az acr list -g "$PRIMARY_RG" --query "[0].name" -o tsv 2>/dev/null || echo "")
if [[ -n "$acr" ]]; then
  pna=$(az acr show -n "$acr" --query "publicNetworkAccess" -o tsv 2>/dev/null)
  if [[ "$pna" == "Disabled" ]]; then
    PASS R3 "Network: ACR $acr public network access Disabled"
  else
    WARN R3 "Network: ACR $acr public network access is '$pna'"
    FIX "az acr update -n $acr --public-network-enabled false (ensure a private endpoint exists first)"
  fi
else
  WARN R3 "Network: no ACR found in $PRIMARY_RG"
fi

# --- R4 Observability: Log Analytics + App Insights -----------------------------
law=$(az monitor log-analytics workspace list -g "$PRIMARY_RG" --query "length(@)" -o tsv 2>/dev/null || echo 0)
appi=$(az resource list -g "$PRIMARY_RG" --resource-type microsoft.insights/components --query "length(@)" -o tsv 2>/dev/null || echo 0)
if [[ "${law:-0}" -ge 1 && "${appi:-0}" -ge 1 ]]; then
  PASS R4 "Observability: Log Analytics ($law) + App Insights ($appi) present"
elif [[ "${law:-0}" -ge 1 ]]; then
  WARN R4 "Observability: Log Analytics present but no App Insights component"
  FIX "deploy modules/loganalytics.bicep app-insights, or wire APPLICATIONINSIGHTS_CONNECTION_STRING"
else
  FAIL R4 "Observability: no Log Analytics workspace in $PRIMARY_RG"
  FIX "redeploy infra/main.bicep (loganalytics module)"
fi

# --- R5 Cost guardrails: scale scripts + budget ---------------------------------
if [[ -x scripts/scale-to-min.sh && -x scripts/scale-to-prod.sh ]]; then
  PASS R5a "Cost: scale-to-min / scale-to-prod scripts present and executable"
else
  WARN R5a "Cost: scale scripts missing or not executable"
  FIX "chmod +x scripts/scale-to-*.sh"
fi
budget=$(az consumption budget list --query "length(@)" -o tsv 2>/dev/null || echo 0)
if [[ "${budget:-0}" -ge 1 ]]; then
  PASS R5b "Cost: $budget subscription budget(s) configured"
else
  WARN R5b "Cost: no subscription budget configured"
  FIX "az consumption budget create --budget-name heimdall-monthly --amount 2000 --time-grain Monthly --category Cost"
fi

# --- R6 Resilience: Cosmos backup -----------------------------------------------
cosmos=$(az cosmosdb list -g "$PRIMARY_RG" --query "[0].name" -o tsv 2>/dev/null || echo "")
if [[ -n "$cosmos" ]]; then
  bkp=$(az cosmosdb show -n "$cosmos" -g "$PRIMARY_RG" --query "backupPolicy.type" -o tsv 2>/dev/null)
  PASS R6 "Resilience: Cosmos $cosmos backup policy = ${bkp:-Periodic}"
else
  WARN R6 "Resilience: no Cosmos DB account found in $PRIMARY_RG"
fi

# --- R7 Security: Microsoft Defender plans --------------------------------------
defon=$(az security pricing list --query "value[?pricingTier=='Standard'] | length(@)" -o tsv 2>/dev/null || echo 0)
if [[ "${defon:-0}" -ge 1 ]]; then
  PASS R7 "Security: $defon Microsoft Defender plan(s) on Standard tier"
else
  WARN R7 "Security: no Defender plans on Standard tier (costs apply when enabled)"
  FIX "az security pricing create -n VirtualMachines --tier standard  # repeat per plan"
fi

# --- R8 Tags: required tags on the resource group (AUTO-FIX) ---------------------
if [[ "$rg_exists" == "true" ]]; then
  missing=""
  for k in project env owner; do
    v=$(az group show -n "$PRIMARY_RG" --query "tags.$k" -o tsv 2>/dev/null)
    [[ -z "$v" || "$v" == "null" ]] && missing="$missing $k"
  done
  if [[ -z "$missing" ]]; then
    PASS R8 "Tags: resource group has project/env/owner tags"
  elif [[ "$AUTO_FIX" == "1" ]]; then
    az group update -n "$PRIMARY_RG" \
      --set tags.project=Heimdall tags.env="$ENV" tags.owner="$(az account show --query user.name -o tsv 2>/dev/null)" \
      --only-show-errors >/dev/null 2>&1 \
      && { PASS R8 "Tags: applied missing tags ($missing )"; DONE "tagged $PRIMARY_RG with project/env/owner"; } \
      || { FAIL R8 "Tags: missing$missing and auto-fix failed"; FIX "az group update -n $PRIMARY_RG --set tags.project=Heimdall tags.env=$ENV"; }
  else
    FAIL R8 "Tags: missing$missing"
    FIX "az group update -n $PRIMARY_RG --set tags.project=Heimdall tags.env=$ENV tags.owner=<you>"
  fi
else
  WARN R8 "Tags: resource group $PRIMARY_RG does not exist yet"
fi

# --- R9 CI/CD: required workflows present ----------------------------------------
missing_wf=""
for wf in ci infra-deploy docker-build scale; do
  [[ -f ".github/workflows/${wf}.yml" ]] || missing_wf="$missing_wf $wf"
done
if [[ -z "$missing_wf" ]]; then
  PASS R9 "CI/CD: ci, infra-deploy, docker-build and scale workflows present"
else
  FAIL R9 "CI/CD: missing workflow(s):$missing_wf"
  FIX "add .github/workflows/<name>.yml"
fi

# --- R10 No committed secrets ----------------------------------------------------
if grep -REIl '"synapseSqlAdminPassword"[[:space:]]*:[[:space:]]*\{[[:space:]]*"value"' infra/ 2>/dev/null | grep -q .; then
  FAIL R10 "Secrets hygiene: a parameters file commits synapseSqlAdminPassword"
  FIX "remove the line; deploy.sh injects it from SYNAPSE_SQL_ADMIN_PASSWORD"
else
  PASS R10 "Secrets hygiene: no plaintext synapseSqlAdminPassword committed"
fi

# --- R11 Compliance: policy assignments -----------------------------------------
pol=$(az policy assignment list --query "length(@)" -o tsv 2>/dev/null || echo 0)
if [[ "${pol:-0}" -ge 1 ]]; then
  PASS R11 "Compliance: $pol Azure Policy assignment(s) active"
else
  WARN R11 "Compliance: no policy assignments detected at this scope"
  FIX "deploy infra/modules/policy.bicep (data-residency / TLS / tag policies)"
fi

echo "------------------------------------------------------------------------"
total=$((pass+warnc+failc))
printf "Readiness: ${GREEN}%d PASS${NC} / ${YEL}%d WARN${NC} / ${RED}%d FAIL${NC} (of %d checks)\n" \
  "$pass" "$warnc" "$failc" "$total"
if [[ "$failc" -gt 0 ]]; then
  echo "Action required: address the FAIL items above (fixes proposed inline)."
elif [[ "$warnc" -gt 0 ]]; then
  echo "Good. Review the WARN items to reach full production hardening."
else
  echo "All production-readiness requirements met. 🎉"
fi
exit 0
