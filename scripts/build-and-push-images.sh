#!/usr/bin/env bash
# ============================================================================
# build-and-push-images.sh — build all 4 service images via ACR Tasks
# ----------------------------------------------------------------------------
# Uses `az acr build` so no local Docker daemon is required. Sources the
# ACR_LOGIN_SERVER from .env.deployed produced by deploy.sh.
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env.deployed ]]; then
  echo "ERROR: .env.deployed not found. Run scripts/deploy.sh first."
  exit 1
fi
# shellcheck disable=SC1091
source .env.deployed

ACR_NAME="${ACR_LOGIN_SERVER%%.*}"
TAG="${TAG:-latest}"

declare -a SERVICES=(
  "scoring-api:services/scoring-api"
  "agentic-orchestrator:services/agentic-orchestrator"
  "transaction-simulator:services/transaction-simulator"
  "eba-reporter:services/eba-reporter"
)

for entry in "${SERVICES[@]}"; do
  name="${entry%%:*}"
  ctx="${entry##*:}"
  echo "==> Building heimdall/${name}:${TAG} from ${ctx}"
  az acr build \
    --registry "$ACR_NAME" \
    --image "heimdall/${name}:${TAG}" \
    --file "${ctx}/Dockerfile" \
    "${ctx}"
done

echo "==> Done. All images pushed to ${ACR_LOGIN_SERVER}."
