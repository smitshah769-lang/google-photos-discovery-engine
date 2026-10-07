#!/usr/bin/env bash
# Pack snapshot + RAG index for one upload to a cloud VM (~200MB). Does not include raw payloads.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${1:-4ad39133-1e6c-4146-99a0-7d68dfe72020}"
OUT="${2:-$ROOT/review-bundle-${RUN_ID}.tar.gz}"

DB="$ROOT/data/snapshot.db"
RAG="$ROOT/data/rag/${RUN_ID}.json"
if [[ ! -f "$DB" ]]; then
  echo "Missing $DB" >&2
  exit 1
fi
if [[ ! -f "$RAG" ]]; then
  echo "Missing $RAG" >&2
  exit 1
fi

echo "Packing into $OUT ..."
tar -czf "$OUT" -C "$ROOT/data" snapshot.db -C "$ROOT/data/rag" "${RUN_ID}.json"
echo "Done. Upload with: scp \"$OUT\" ubuntu@YOUR_VM_IP:~/"
echo "Run id: $RUN_ID"
