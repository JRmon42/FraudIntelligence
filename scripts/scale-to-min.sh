#!/usr/bin/env bash
# ============================================================================
# scale-to-min.sh — pause/scale-down all expensive resources
# ============================================================================
set -euo pipefail

SUBSCRIPTION_ID="ea8d83f8-8538-4914-ae12-24f954d61638"
PRIMARY_RG="fraudintelligence_rg"
DR_RG="fraudintelligence_dr_rg"
ENV="${ENV:-prod}"
PRIMARY_RC="swc"
DR_RC="neu"

az account set --subscription "$SUBSCRIPTION_ID"

echo "==> Pausing Fabric capacity"
FAB="fabfraudintel${ENV}${PRIMARY_RC}"
az resource invoke-action \
  --action suspend \
  --resource-type Microsoft.Fabric/capacities \
  --name "$FAB" \
  --resource-group "$PRIMARY_RG" \
  --api-version 2023-11-01 || echo "  (fabric already paused or missing)"

echo "==> Stopping Stream Analytics job"
az stream-analytics job stop \
  --resource-group "$PRIMARY_RG" \
  --name "asa-fraudintel-${ENV}-${PRIMARY_RC}" || true

echo "==> Scaling ACA apps to 0 replicas"
for region in "$PRIMARY_RG:$PRIMARY_RC" "$DR_RG:$DR_RC"; do
  RG="${region%%:*}"
  RC="${region##*:}"
  for app in "ca-orchestrator-${ENV}-${RC}" "ca-scoring-${ENV}-${RC}"; do
    az containerapp update -n "$app" -g "$RG" --min-replicas 0 --max-replicas 1 || true
  done
done

echo "==> Scaling AML compute clusters to 0"
AML_WS="mlw-fraudintel-${ENV}-${PRIMARY_RC}"
for cluster in $(az ml compute list -w "$AML_WS" -g "$PRIMARY_RG" --query "[?type=='AmlCompute'].name" -o tsv 2>/dev/null || true); do
  az ml compute update -n "$cluster" -w "$AML_WS" -g "$PRIMARY_RG" --min-instances 0 --max-instances 0 || true
done

echo "==> Scaling Cosmos containers to manual 400 RU"
COSMOS="cosmos-fraudintel-${ENV}-${PRIMARY_RC}"
for c in transactions cards merchants decisions features; do
  az cosmosdb sql container throughput update \
    -a "$COSMOS" -g "$PRIMARY_RG" -d fraud -n "$c" --throughput 400 || true
done
az cosmosdb gremlin graph throughput update \
  -a "$COSMOS" -g "$PRIMARY_RG" -d fraudgraph -n rings --throughput 400 || true

echo "==> Scaled to minimum."
