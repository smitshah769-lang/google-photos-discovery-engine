#!/usr/bin/env bash
# Stream bundle to VM without keeping a second copy (needs existing pack or pipes tar).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${1:-4ad39133-1e6c-4146-99a0-7d68dfe72020}"
VM="${2:?Usage: $0 [run-id] user@host (e.g. ubuntu@129.12.34.56)}"

DB="$ROOT/data/snapshot.db"
RAG="$ROOT/data/rag/${RUN_ID}.json"
for f in "$DB" "$RAG"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing $f" >&2
    exit 1
  fi
done

echo "Uploading snapshot + RAG to $VM (streaming tar, no local .tar.gz required) ..."
tar -czf - -C "$ROOT/data" snapshot.db -C "$ROOT/data/rag" "${RUN_ID}.json" | ssh "$VM" "mkdir -p ~/review-bundle && tar -xzf - -C ~/review-bundle && echo 'Extracted to ~/review-bundle/'"
