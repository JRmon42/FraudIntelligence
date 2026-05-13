#!/usr/bin/env bash
# ============================================================================
# smoke-test.sh — basic post-deploy validation
# ============================================================================
set -euo pipefail

if [[ ! -f .env.deployed ]]; then
  echo "ERROR: .env.deployed not found. Run scripts/deploy.sh first."
  exit 1
fi
# shellcheck disable=SC1091
source .env.deployed

SCORING_URL="https://${SCORING_FRONTDOOR_HOST}"
SAMPLES="${SAMPLES:-100}"

echo "==> 1. Health check: $SCORING_URL/healthz"
curl --fail --silent --show-error --max-time 10 "$SCORING_URL/healthz" || {
  echo "FAIL: scoring health check"; exit 1; }
echo "  OK"

echo "==> 2. Sending $SAMPLES synthetic transactions"
for i in $(seq 1 "$SAMPLES"); do
  payload=$(cat <<JSON
{
  "transactionId": "smoke-$(date +%s%N)-$i",
  "cardId": "card-$((RANDOM % 1000))",
  "merchantId": "mer-$((RANDOM % 200))",
  "amount": $((RANDOM % 50000)).$((RANDOM % 100)),
  "currency": "EUR",
  "eventTimestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
)
  curl --silent --show-error --max-time 5 \
       -X POST "$SCORING_URL/score" \
       -H 'Content-Type: application/json' \
       -d "$payload" > /dev/null || echo "  (sample $i failed)"
done
echo "  Sent $SAMPLES transactions"

echo "==> 3. Power BI dataset row count"
if [[ -z "${POWERBI_WORKSPACE_ID:-}" || -z "${POWERBI_DATASET_ID:-}" ]]; then
  echo "  SKIP — set POWERBI_WORKSPACE_ID and POWERBI_DATASET_ID env vars"
else
  TOKEN=$(az account get-access-token --resource https://analysis.windows.net/powerbi/api --query accessToken -o tsv)
  curl --fail --silent --show-error \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -X POST "https://api.powerbi.com/v1.0/myorg/groups/${POWERBI_WORKSPACE_ID}/datasets/${POWERBI_DATASET_ID}/executeQueries" \
    -d '{"queries":[{"query":"EVALUATE ROW(\"rows\", COUNTROWS(transactions))"}]}'
  echo
fi

echo "==> Smoke test complete"
