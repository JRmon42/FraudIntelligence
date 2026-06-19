#!/usr/bin/env bash
# ============================================================================
# demo-web.sh — launch the Heimdall live demo web console.
#
# Dependency-free: uses python3 + stdlib only (no pip installs, no curl/jq).
# Serves a single-page dashboard from which you can launch every demo step and
# watch transaction status + analysis metrics stream in live. Reuses the same
# scoring code path as scripts/demo.sh (demo_client.py) against the deployed
# scoring API (SCORING_FRONTDOOR_HOST from .env.deployed).
#
# Examples:
#   ./scripts/demo-web.sh                      # http://127.0.0.1:8800
#   ./scripts/demo-web.sh --port 9000
#   ./scripts/demo-web.sh --host 0.0.0.0       # expose on the LAN
#   ./scripts/demo-web.sh --scoring-host my.host.azurefd.net
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required but not found on PATH." >&2
  exit 1
fi

exec python3 "$SCRIPT_DIR/demo_web.py" "$@"
