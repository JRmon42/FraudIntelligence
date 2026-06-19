#!/usr/bin/env bash
# ============================================================================
# smoke-test.sh — basic post-deploy validation
#
# Validates the REAL scoring contract: GET /healthz + POST /v1/score with the
# snake_case ScoreRequest schema (extra=forbid). Works without curl/jq by
# delegating the health check and request load to scripts/demo_client.py.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f .env.deployed ]]; then
  echo "ERROR: .env.deployed not found. Run scripts/deploy.sh first."
  exit 1
fi
# shellcheck disable=SC1091
source .env.deployed

SAMPLES="${SAMPLES:-100}"

echo "==> 1. Health check (/healthz + /readyz)"
python3 "$SCRIPT_DIR/demo_client.py" health

echo "==> 2. Sending $SAMPLES synthetic transactions to POST /v1/score"
python3 "$SCRIPT_DIR/demo_client.py" load --tps "$SAMPLES" --duration 1 --max "$SAMPLES" --workers 20

echo "==> 3. Power BI dataset row count"
if [[ -z "${POWERBI_WORKSPACE_ID:-}" || -z "${POWERBI_DATASET_ID:-}" ]]; then
  echo "  SKIP — set POWERBI_WORKSPACE_ID and POWERBI_DATASET_ID env vars"
else
  TOKEN=$(az account get-access-token --resource https://analysis.windows.net/powerbi/api --query accessToken -o tsv)
  python3 - "$POWERBI_WORKSPACE_ID" "$POWERBI_DATASET_ID" "$TOKEN" <<'PY'
import json, sys, urllib.request
ws, ds, token = sys.argv[1], sys.argv[2], sys.argv[3]
url = f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{ds}/executeQueries"
body = json.dumps({"queries": [{"query": 'EVALUATE ROW("rows", COUNTROWS(transactions))'}]}).encode()
req = urllib.request.Request(url, data=body, method="POST", headers={
    "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
print(urllib.request.urlopen(req, timeout=30).read().decode())
PY
fi

echo "==> Smoke test complete"
