#!/usr/bin/env bash
# Share dashboard + Ask-the-snapshot with 3–5 reviewers (not localhost-only).
#
# 1) Set credentials (required when not binding to 127.0.0.1):
#    export DISCOVERY_BASIC_USER=reviewer
#    export DISCOVERY_BASIC_PASSWORD='choose-a-strong-password'
#    export NEXT_PUBLIC_DISCOVERY_BASIC_AUTH="$DISCOVERY_BASIC_USER:$DISCOVERY_BASIC_PASSWORD"
#
# 2) Run on a small VM or your machine with a tunnel:
#    DISCOVERY_BIND_HOST=0.0.0.0 ./scripts/serve-for-reviewers.sh <run-id>
#
# 3) Put HTTPS in front (Cloudflare Tunnel, ngrok, or your load balancer) and share that URL.
#
# Requires: pip install -e ".[analysis]" (embeddings), Node for the UI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${1:?Usage: $0 <analysis_run_id>}"
export DISCOVERY_BIND_HOST="${DISCOVERY_BIND_HOST:-127.0.0.1}"
export DISCOVERY_BIND_PORT="${DISCOVERY_BIND_PORT:-8765}"
export DISCOVERY_API_URL="${DISCOVERY_API_URL:-http://127.0.0.1:${DISCOVERY_BIND_PORT}}"
export NEXT_PUBLIC_DISCOVERY_API_URL="${NEXT_PUBLIC_DISCOVERY_API_URL:-$DISCOVERY_API_URL}"

if [[ "$DISCOVERY_BIND_HOST" != "127.0.0.1" && "$DISCOVERY_BIND_HOST" != "localhost" ]]; then
  if [[ -z "${DISCOVERY_BASIC_USER:-}" || -z "${DISCOVERY_BASIC_PASSWORD:-}" ]]; then
    echo "Set DISCOVERY_BASIC_USER and DISCOVERY_BASIC_PASSWORD before binding to $DISCOVERY_BIND_HOST." >&2
    exit 1
  fi
fi

exec "$ROOT/scripts/serve-artifact.sh" "$RUN_ID"
