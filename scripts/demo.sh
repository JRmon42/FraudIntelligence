#!/usr/bin/env bash
# ============================================================================
# demo.sh — Heimdall live demo driver (thin wrapper over demo_client.py)
#
# Dependency-free: uses python3 + stdlib only (no curl/jq required).
# Reads the scoring host from .env.deployed (SCORING_FRONTDOOR_HOST).
#
# Examples:
#   ./scripts/demo.sh health
#   ./scripts/demo.sh score --profile high
#   ./scripts/demo.sh load --tps 2000 --duration 120        # representative burst (capped)
#   ./scripts/demo.sh inject --pattern ring --cards 10 --merchants 3
#   ./scripts/demo.sh all
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required but not found on PATH." >&2
  exit 1
fi

exec python3 "$SCRIPT_DIR/demo_client.py" "$@"
