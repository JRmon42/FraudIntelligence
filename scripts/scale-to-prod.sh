#!/usr/bin/env bash
# ============================================================================
# scale-to-prod.sh — restore production scale
# ============================================================================
set -euo pipefail

# All settings are overridable via env vars so the script runs identically
# locally and in GitHub Actions (which injects AZURE_SUBSCRIPTION_ID via OIDC).
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-${AZURE_SUBSCRIPTION_ID:-ea8d83f8-8538-4914-ae12-24f954d61638}}"
PRIMARY_RG="${PRIMARY_RG:-heimdall_rg}"
DR_RG="${DR_RG:-heimdall_dr_rg}"
ENV="${ENV:-prod}"
PRIMARY_RC="${PRIMARY_RC:-swc}"
DR_RC="${DR_RC:-neu}"

az account set --subscription "$SUBSCRIPTION_ID"

echo "==> Resuming Fabric capacity"
FAB="fabheimdall${ENV}${PRIMARY_RC}"
FAB_STATE=$(az resource show -g "$PRIMARY_RG" -n "$FAB" \
  --resource-type Microsoft.Fabric/capacities --api-version 2023-11-01 \
  --query "properties.state" -o tsv 2>/dev/null || echo "Unknown")
case "$FAB_STATE" in
  Active)
    echo "    Fabric already Active — skipping resume."
    ;;
  Paused)
    az resource invoke-action \
      --action resume \
      --resource-type Microsoft.Fabric/capacities \
      --name "$FAB" \
      --resource-group "$PRIMARY_RG" \
      --api-version 2023-11-01 || \
      echo "    (resume rejected — capacity may be mid-transition; re-run in a minute)"
    ;;
  *)
    # Resuming / Pausing / Scaling / Unknown — transient states reject 'resume'
    # with 'Service is not ready to be updated'. Non-fatal; just report and move on.
    echo "    Fabric is in transitional state '$FAB_STATE' — skipping resume (non-fatal)."
    ;;
esac

echo "==> Starting Stream Analytics job (best-effort)"
# NOTE: The Event Hubs namespace is private-endpoint-only (publicNetworkAccess=Disabled).
# A standard ASA *cloud* job cannot reach a private-only namespace, so this start may
# fail with "Ip has been prevented to connect to the endpoint". That is expected and
# does NOT affect the real-time scoring API demo. To run ASA live you must either
# enable trusted-service access on the namespace or use an ASA dedicated cluster
# (see docs/runbook.md → "Stream Analytics & private networking").
if ! az stream-analytics job start \
  --resource-group "$PRIMARY_RG" \
  --name "asa-heimdall-${ENV}-${PRIMARY_RC}" \
  --output-start-mode JobStartTime 2>/tmp/asa_start.err; then
  echo "    (ASA did not start — see note above; continuing. Detail:)"
  sed 's/^/      /' /tmp/asa_start.err | head -4 || true
fi

echo "==> Scaling ACA apps back up"
RC=$PRIMARY_RC; RG=$PRIMARY_RG
az containerapp update -n "ca-orchestrator-${ENV}-${RC}" -g "$RG" --min-replicas 1 --max-replicas 10 || true
az containerapp update -n "ca-scoring-${ENV}-${RC}"      -g "$RG" --min-replicas 2 --max-replicas 30 || true
RC=$DR_RC; RG=$DR_RG
az containerapp update -n "ca-orchestrator-${ENV}-${RC}" -g "$RG" --min-replicas 1 --max-replicas 10 || true
az containerapp update -n "ca-scoring-${ENV}-${RC}"      -g "$RG" --min-replicas 2 --max-replicas 30 || true

echo "==> Restoring AML compute (1..4)"
AML_WS="mlw-heimdall-${ENV}-${PRIMARY_RC}"
for cluster in $(az ml compute list -w "$AML_WS" -g "$PRIMARY_RG" --query "[?type=='AmlCompute'].name" -o tsv 2>/dev/null || true); do
  az ml compute update -n "$cluster" -w "$AML_WS" -g "$PRIMARY_RG" --min-instances 1 --max-instances 4 || true
done

echo "==> Restoring Cosmos throughput (autoscale 4000)"
COSMOS="cosmos-heimdall-${ENV}-${PRIMARY_RC}"
for c in transactions cards merchants decisions features; do
  az cosmosdb sql container throughput migrate -a "$COSMOS" -g "$PRIMARY_RG" -d fraud -n "$c" --throughput-type autoscale || true
  az cosmosdb sql container throughput update  -a "$COSMOS" -g "$PRIMARY_RG" -d fraud -n "$c" --max-throughput 4000 || true
done
az cosmosdb gremlin graph throughput migrate -a "$COSMOS" -g "$PRIMARY_RG" -d fraudgraph -n rings --throughput-type autoscale || true
az cosmosdb gremlin graph throughput update  -a "$COSMOS" -g "$PRIMARY_RG" -d fraudgraph -n rings --max-throughput 4000 || true

echo "==> Scaled to production."
