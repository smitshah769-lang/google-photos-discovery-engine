#!/usr/bin/env bash
# Run ON a fresh Ubuntu 22.04/24.04 VM (Oracle Always Free ARM recommended).
# Usage: curl -fsSL ... | bash   OR   bash vm-bootstrap.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/smitshah769-lang/google-photos-discovery-engine.git}"
PROJECT_DIR="${PROJECT_DIR:-$HOME/google-photos-discovery-engine}"
RUN_ID="${RUN_ID:-4ad39133-1e6c-4146-99a0-7d68dfe72020}"
REVIEWER_USER="${DISCOVERY_BASIC_USER:-reviewer}"
REVIEWER_PASS="${DISCOVERY_BASIC_PASSWORD:-}"

echo "==> System packages"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  git python3 python3-pip python3-venv curl ca-certificates

if ! command -v node >/dev/null 2>&1 || [[ "$(node -v 2>/dev/null)" < "v18" ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y -qq nodejs
fi

echo "==> Clone repo"
if [[ ! -d "$PROJECT_DIR" ]]; then
  git clone "$REPO_URL" "$PROJECT_DIR"
fi
cd "$PROJECT_DIR"

echo "==> Data layout"
mkdir -p data/rag
if [[ -d "$HOME/review-bundle" ]]; then
  cp -f "$HOME/review-bundle/snapshot.db" data/snapshot.db
  cp -f "$HOME/review-bundle/${RUN_ID}.json" "data/rag/${RUN_ID}.json"
  echo "Installed bundle from ~/review-bundle/"
else
  echo "WARN: No ~/review-bundle — upload data first (scripts/upload-review-bundle.sh from your Mac)." >&2
fi

if [[ -z "$REVIEWER_PASS" ]]; then
  REVIEWER_PASS="$(openssl rand -hex 8)"
  echo "Generated DISCOVERY_BASIC_PASSWORD=$REVIEWER_PASS"
fi

ENV_FILE="$PROJECT_DIR/.env"
cat > "$ENV_FILE" <<EOF
DISCOVERY_BASIC_USER=$REVIEWER_USER
DISCOVERY_BASIC_PASSWORD=$REVIEWER_PASS
NEXT_PUBLIC_DISCOVERY_BASIC_AUTH=$REVIEWER_USER:$REVIEWER_PASS
DISCOVERY_API_URL=http://127.0.0.1:8765
DISCOVERY_BIND_HOST=127.0.0.1
EOF
chmod 600 "$ENV_FILE"
cp "$ENV_FILE" app/.env.local

echo "==> Python deps (models download on first search, not here)"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip
pip install -q -e ".[analysis]"

echo "==> Next.js"
cd app
npm ci --silent
npm run build
cd ..

echo "==> systemd units"
sudo tee /etc/systemd/system/discovery-api.service >/dev/null <<EOF
[Unit]
Description=Google Photos Discovery read API
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$PROJECT_DIR/.venv/bin/python3 -m pipeline serve $RUN_ID --host 127.0.0.1 --port 8765
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/discovery-ui.service >/dev/null <<EOF
[Unit]
Description=Google Photos Discovery Next.js UI
After=network.target discovery-api.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR/app
EnvironmentFile=$ENV_FILE
Environment=PORT=3000
Environment=HOSTNAME=0.0.0.0
ExecStart=/usr/bin/npm run start -- --port 3000 --hostname 0.0.0.0
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable discovery-api discovery-ui
sudo systemctl restart discovery-api discovery-ui

echo ""
echo "==> VM bootstrap complete"
echo "API (internal): http://127.0.0.1:8765"
echo "UI (open firewall port 3000 OR use Cloudflare Tunnel): http://$(curl -s ifconfig.me 2>/dev/null || echo YOUR_VM_IP):3000"
echo "Basic auth user: $REVIEWER_USER"
echo "Basic auth password: $REVIEWER_PASS  (also in $ENV_FILE)"
echo ""
echo "Oracle: open ingress TCP 3000 for reviewers, or prefer Cloudflare Tunnel → localhost:3000"
echo "Share NEXT_PUBLIC_DISCOVERY_BASIC_AUTH with reviewers for the browser (same user:pass)."
