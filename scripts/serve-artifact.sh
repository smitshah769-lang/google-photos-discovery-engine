#!/usr/bin/env bash
# Serve frozen snapshot APIs (8765) + Next.js research UI (3000). No pipeline jobs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if ! python3 -c "import sentence_transformers" 2>/dev/null; then
  echo "RAG search needs sentence-transformers. Run: pip install -e '.[analysis]'" >&2
fi
RUN_ID="${1:-}"
EXPORT_DIR="${EXPORT_DIR:-}"
if [[ -z "$RUN_ID" && -z "$EXPORT_DIR" ]]; then
  echo "Usage: $0 <analysis_run_id>" >&2
  echo "   or: EXPORT_DIR=data/exports/<run-id> $0" >&2
  exit 1
fi
HOST="${DISCOVERY_BIND_HOST:-127.0.0.1}"
PORT="${DISCOVERY_BIND_PORT:-8765}"
if [[ -n "$EXPORT_DIR" ]]; then
  python -m pipeline serve ${RUN_ID:+$RUN_ID} --export-dir "$EXPORT_DIR" --host "$HOST" --port "$PORT" &
else
  python -m pipeline serve "$RUN_ID" --host "$HOST" --port "$PORT" &
fi
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT
export DISCOVERY_API_URL="${DISCOVERY_API_URL:-http://127.0.0.1:8765}"
export NEXT_PUBLIC_DISCOVERY_API_URL="$DISCOVERY_API_URL"
cd "$ROOT/app"
npm run dev -- --port 3000 --hostname 127.0.0.1
