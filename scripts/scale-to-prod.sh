#!/usr/bin/env bash
# ============================================================================
# scale-to-prod.sh — restore production scale
# ============================================================================
set -euo pipefail

SUBSCRIPTION_ID="ea8d83f8-8538-4914-ae12-24f954d61638"
PRIMARY_RG="fraudintelligence_rg"
DR_RG="fraudintelligence_dr_rg"
ENV="${ENV:-prod}"
PRIMARY_RC="swc"
DR_RC="neu"

az account set --subscription "$SUBSCRIPTION_ID"

echo "==> Resuming Fabric capacity"
FAB="fabfraudintel${ENV}${PRIMARY_RC}"
az resource invoke-action \
  --action resume \
  --resource-type Microsoft.Fabric/capacities \
  --name "$FAB" \
  --resource-group "$PRIMARY_RG" \
  --api-version 2023-11-01 || true

echo "==> Starting Stream Analytics job"
az stream-analytics job start \
  --resource-group "$PRIMARY_RG" \
  --name "asa-fraudintel-${ENV}-${PRIMARY_RC}" \
  --output-start-mode JobStartTime || true

echo "==> Scaling ACA apps back up"
RC=$PRIMARY_RC; RG=$PRIMARY_RG
az containerapp update -n "ca-orchestrator-${ENV}-${RC}" -g "$RG" --min-replicas 1 --max-replicas 10 || true
az containerapp update -n "ca-scoring-${ENV}-${RC}"      -g "$RG" --min-replicas 2 --max-replicas 30 || true
RC=$DR_RC; RG=$DR_RG
az containerapp update -n "ca-orchestrator-${ENV}-${RC}" -g "$RG" --min-replicas 1 --max-replicas 10 || true
az containerapp update -n "ca-scoring-${ENV}-${RC}"      -g "$RG" --min-replicas 2 --max-replicas 30 || true

echo "==> Restoring AML compute (1..4)"
AML_WS="mlw-fraudintel-${ENV}-${PRIMARY_RC}"
for cluster in $(az ml compute list -w "$AML_WS" -g "$PRIMARY_RG" --query "[?type=='AmlCompute'].name" -o tsv 2>/dev/null || true); do
  az ml compute update -n "$cluster" -w "$AML_WS" -g "$PRIMARY_RG" --min-instances 1 --max-instances 4 || true
done

echo "==> Restoring Cosmos throughput (autoscale 4000)"
COSMOS="cosmos-fraudintel-${ENV}-${PRIMARY_RC}"
for c in transactions cards merchants decisions features; do
  az cosmosdb sql container throughput migrate -a "$COSMOS" -g "$PRIMARY_RG" -d fraud -n "$c" --throughput-type autoscale || true
  az cosmosdb sql container throughput update  -a "$COSMOS" -g "$PRIMARY_RG" -d fraud -n "$c" --max-throughput 4000 || true
done
az cosmosdb gremlin graph throughput migrate -a "$COSMOS" -g "$PRIMARY_RG" -d fraudgraph -n rings --throughput-type autoscale || true
az cosmosdb gremlin graph throughput update  -a "$COSMOS" -g "$PRIMARY_RG" -d fraudgraph -n rings --max-throughput 4000 || true

echo "==> Scaled to production."
