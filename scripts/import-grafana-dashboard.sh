#!/usr/bin/env bash
# ============================================================================
# import-grafana-dashboard.sh
# Imports a dashboard JSON model into Azure Managed Grafana.
#
# Azure Managed Grafana dashboards are NOT ARM resources, so they cannot be
# declared in Bicep. This script renders the templated JSON under
# dashboards/grafana/ and pushes it via the Grafana HTTP API using an Entra
# (AAD) access token. Run it after `infra` is deployed.
#
# Requires: az (logged in, with Grafana Admin/Editor on the instance), python3.
# Env overrides (all have sensible defaults for the prod-swc deployment):
#   GRAFANA_NAME, RESOURCE_GROUP, SUBSCRIPTION_ID, APPINSIGHTS_RESOURCE_ID,
#   SCORING_APP_NAME, COSMOS_ACCOUNT_NAME, GRAFANA_AZ_MONITOR_DS_UID,
#   DASHBOARD_FILE
# ============================================================================
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-heimdall_rg}"
GRAFANA_NAME="${GRAFANA_NAME:-graf-heimdall-prod-swc}"
SCORING_APP_NAME="${SCORING_APP_NAME:-ca-scoring-prod-swc}"
COSMOS_ACCOUNT_NAME="${COSMOS_ACCOUNT_NAME:-cosmos-heimdall-prod-swc}"
GRAFANA_AZ_MONITOR_DS_UID="${GRAFANA_AZ_MONITOR_DS_UID:-azure-monitor-oob}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASHBOARD_FILE="${DASHBOARD_FILE:-$HERE/dashboards/grafana/scoring-api-slo.json}"
# Azure Managed Grafana first-party AAD application (token audience).
GRAFANA_AAD_APP="ce34e7e5-485f-4d76-964f-b3d2b16d1e4f"

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"
APPINSIGHTS_RESOURCE_ID="${APPINSIGHTS_RESOURCE_ID:-$(az resource list -g "$RESOURCE_GROUP" \
  --resource-type Microsoft.Insights/components --query "[0].id" -o tsv)}"

ENDPOINT="$(az resource show -g "$RESOURCE_GROUP" -n "$GRAFANA_NAME" \
  --resource-type Microsoft.Dashboard/grafana --query properties.endpoint -o tsv)"
TOKEN="$(az account get-access-token --resource "$GRAFANA_AAD_APP" --query accessToken -o tsv)"

echo "==> Grafana endpoint : $ENDPOINT"
echo "==> Dashboard        : $DASHBOARD_FILE"
echo "==> App Insights     : $APPINSIGHTS_RESOURCE_ID"

SUBSCRIPTION_ID="$SUBSCRIPTION_ID" RESOURCE_GROUP="$RESOURCE_GROUP" \
APPINSIGHTS_RESOURCE_ID="$APPINSIGHTS_RESOURCE_ID" SCORING_APP_NAME="$SCORING_APP_NAME" \
COSMOS_ACCOUNT_NAME="$COSMOS_ACCOUNT_NAME" GRAFANA_AZ_MONITOR_DS_UID="$GRAFANA_AZ_MONITOR_DS_UID" \
ENDPOINT="$ENDPOINT" TOKEN="$TOKEN" DASHBOARD_FILE="$DASHBOARD_FILE" \
python3 - <<'PY'
import json, os, string, urllib.request, sys

raw = open(os.environ["DASHBOARD_FILE"]).read()
rendered = string.Template(raw).safe_substitute({
    k: os.environ[k] for k in (
        "SUBSCRIPTION_ID", "RESOURCE_GROUP", "APPINSIGHTS_RESOURCE_ID",
        "SCORING_APP_NAME", "COSMOS_ACCOUNT_NAME", "GRAFANA_AZ_MONITOR_DS_UID",
    )
})
model = json.loads(rendered)
model["id"] = None            # let Grafana assign
payload = {"dashboard": model, "overwrite": True, "folderUid": "",
           "message": "Imported by import-grafana-dashboard.sh"}

req = urllib.request.Request(
    os.environ["ENDPOINT"].rstrip("/") + "/api/dashboards/db",
    data=json.dumps(payload).encode(),
    headers={"Authorization": "Bearer " + os.environ["TOKEN"],
             "Content-Type": "application/json"},
    method="POST")
try:
    resp = json.load(urllib.request.urlopen(req, timeout=60))
    print("==> Imported OK:", json.dumps({k: resp.get(k) for k in ("status", "uid", "version", "url")}))
except urllib.error.HTTPError as e:
    print("ERROR", e.code, e.read().decode(errors="replace"), file=sys.stderr)
    sys.exit(1)
PY
echo "==> Done."
