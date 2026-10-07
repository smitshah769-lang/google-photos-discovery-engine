#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi
pip install -e ".[dev]" -q

if [[ -f .env ]]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

if [[ -z "${GOOGLE_CSE_API_KEY:-}" || -z "${GOOGLE_CSE_CX:-}" ]]; then
  echo "Warning: GOOGLE_CSE_API_KEY / GOOGLE_CSE_CX not set — Help Community will rely on browse HTML only."
  echo "Copy .env.example to .env and add CSE credentials for better thread coverage."
fi

python -m pipeline init-db
RUN="$(python -m pipeline new-run)"
echo "Analysis run: $RUN"
echo "Starting live collect (this may take a long time)..."
python -m pipeline collect "$RUN"
python -m pipeline status "$RUN"
echo ""
echo "Next: python -m pipeline normalize $RUN"
echo "Then: python -m pipeline status $RUN"
