#!/usr/bin/env bash
# ============================================================================
# run_rai_scorecard.sh — Register the Heimdall fraud ensemble and generate a
# Responsible AI dashboard + downloadable scorecard in Azure ML Studio.
#
# This makes the "Responsible AI" blade in mlw-heimdall-<env>-<region> real:
# it registers the SERVED sklearn pipeline as an MLflow model, publishes the
# train/test sets as MLTable data assets, then submits the RAI pipeline
# (ml/aml_jobs/rai_scorecard.yml). The result is visible under
#   Azure ML Studio -> Models -> fraud-intel-ensemble-sklearn -> Responsible AI
# with a "Download scorecard (PDF)" button.
#
# Every setting is overridable via environment variables:
#   SUBSCRIPTION_ID / AZURE_SUBSCRIPTION_ID  target subscription (default: az login)
#   RESOURCE_GROUP                           resource group      (default: rg-heimdall-prod-swc)
#   WORKSPACE                                AML workspace       (default: mlw-heimdall-prod-swc)
#   SKIP_TRAIN=1                             reuse existing ml/artifacts (skip training)
#
# Requires the Azure ML CLI v2 extension (`az extension add -n ml`). Because the
# workspace is private (managed VNet, publicNetworkAccess=Disabled), run this
# from a host with line-of-sight to the workspace (Azure Cloud Shell, a jump
# box, or a self-hosted runner in the VNet).
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-${AZURE_SUBSCRIPTION_ID:-}}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-heimdall-prod-swc}"
WORKSPACE="${WORKSPACE:-mlw-heimdall-prod-swc}"
MODEL_NAME="fraud-intel-ensemble-sklearn"
ARTIFACTS="ml/artifacts"
RAI_DATA="ml/aml_jobs/rai_data"

echo "==> Ensuring Azure ML CLI extension is present"
az extension show -n ml >/dev/null 2>&1 || az extension add -n ml -y

AZ=(az)
[[ -n "$SUBSCRIPTION_ID" ]] && AZ+=(--subscription "$SUBSCRIPTION_ID")
DEFAULTS=(--resource-group "$RESOURCE_GROUP" --workspace-name "$WORKSPACE")

# --------------------------------------------------------------------------
# 1) Produce artifacts (sklearn MLflow model + train/test parquet)
# --------------------------------------------------------------------------
if [[ "${SKIP_TRAIN:-0}" != "1" || ! -d "$ARTIFACTS/sklearn-model" ]]; then
  echo "==> Training ensemble to produce MLflow model + RAI datasets"
  python -m ml.train_ensemble --output "$ARTIFACTS/" --smoke 60000
fi
for f in "$ARTIFACTS/sklearn-model/MLmodel" "$ARTIFACTS/train_data.parquet" "$ARTIFACTS/test_data.parquet"; do
  [[ -e "$f" ]] || { echo "ERROR: expected artifact missing: $f" >&2; exit 1; }
done

# --------------------------------------------------------------------------
# 2) Build MLTable folders for the train/test data assets
# --------------------------------------------------------------------------
echo "==> Building MLTable folders"
for split in train test; do
  dir="$RAI_DATA/$split"
  mkdir -p "$dir"
  cp -f "$ARTIFACTS/${split}_data.parquet" "$dir/${split}_data.parquet"
  cat > "$dir/MLTable" <<EOF
paths:
  - file: ./${split}_data.parquet
transformations:
  - read_parquet
EOF
done

# --------------------------------------------------------------------------
# 3) Register data assets (MLTable)
# --------------------------------------------------------------------------
echo "==> Registering MLTable data assets"
"${AZ[@]}" ml data create "${DEFAULTS[@]}" \
  --name fraud-intel-rai-train --type mltable --path "$RAI_DATA/train"
"${AZ[@]}" ml data create "${DEFAULTS[@]}" \
  --name fraud-intel-rai-test  --type mltable --path "$RAI_DATA/test"

# --------------------------------------------------------------------------
# 4) Register the MLflow model
# --------------------------------------------------------------------------
echo "==> Registering MLflow model $MODEL_NAME"
"${AZ[@]}" ml model create "${DEFAULTS[@]}" \
  --name "$MODEL_NAME" --type mlflow_model --path "$ARTIFACTS/sklearn-model" \
  --tags team=fraud-intel task=binary-classification eu_ai_act=high_risk

MODEL_VERSION="$("${AZ[@]}" ml model list "${DEFAULTS[@]}" --name "$MODEL_NAME" \
  --query 'max_by([],&to_number(version)).version' -o tsv 2>/dev/null || echo 1)"
echo "    registered version: $MODEL_VERSION"

# --------------------------------------------------------------------------
# 5) Submit the Responsible AI pipeline
# --------------------------------------------------------------------------
echo "==> Submitting RAI dashboard + scorecard pipeline"
"${AZ[@]}" ml job create "${DEFAULTS[@]}" \
  --file ml/aml_jobs/rai_scorecard.yml \
  --set inputs.model_info="${MODEL_NAME}:${MODEL_VERSION}" \
  --stream

echo "==> Done. Open Azure ML Studio -> Models -> $MODEL_NAME -> Responsible AI"
echo "    to view the dashboard and download the PDF scorecard."
