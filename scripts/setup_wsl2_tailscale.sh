#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${SUDO_USER:-$USER}"
ENV_FILE="/etc/home-cloud/home-cloud.env"
SYSTEMD_UNIT="/etc/systemd/system/home-cloud.service"
NGINX_SITE="/etc/nginx/sites-available/home-cloud"
NGINX_ENABLED="/etc/nginx/sites-enabled/home-cloud"
STORAGE_PATH="/srv/home-cloud-storage"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run this script with sudo: sudo ./scripts/setup_wsl2_tailscale.sh"
    exit 1
fi

if [[ ! -f /etc/os-release ]]; then
    echo "Unsupported Linux distribution. Ubuntu is recommended."
    exit 1
fi

echo "[1/7] Installing required packages"
apt-get update
apt-get install -y python3 python3-venv python3-pip nginx curl

if ! command -v tailscale >/dev/null 2>&1; then
    echo "[2/7] Installing Tailscale"
    curl -fsSL https://tailscale.com/install.sh | sh
else
    echo "[2/7] Tailscale already installed"
fi

echo "[3/7] Preparing Python virtual environment"
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "[4/7] Preparing storage directories"
mkdir -p "$STORAGE_PATH/uploads" "$STORAGE_PATH/home-cloud" "$STORAGE_PATH/trash" "$STORAGE_PATH/temp"
chown -R "$APP_USER":"$APP_USER" "$STORAGE_PATH"

echo "[5/7] Creating environment file"
mkdir -p /etc/home-cloud
if [[ ! -f "$ENV_FILE" ]]; then
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    cat > "$ENV_FILE" <<EOF
APP_CONFIG=production
SECRET_KEY=$SECRET_KEY
SERVER_HOST=127.0.0.1
SERVER_PORT=5000
USE_HTTPS=false
TRUST_PROXY_HEADERS=true
BASE_STORAGE_PATH=$STORAGE_PATH
DATABASE_URL=sqlite:///$STORAGE_PATH/home-cloud/production.db
EOF
    chmod 640 "$ENV_FILE"
fi

echo "[6/7] Installing systemd service and nginx config"
python3 - <<PY
from pathlib import Path
service_tpl = Path(r"$APP_DIR/deploy/systemd/home-cloud.service.template").read_text()
service = service_tpl.replace("__APP_DIR__", r"$APP_DIR").replace("__APP_USER__", r"$APP_USER")
Path(r"$SYSTEMD_UNIT").write_text(service)
PY

cp "$APP_DIR/deploy/nginx/home-cloud.conf.template" "$NGINX_SITE"
ln -sfn "$NGINX_SITE" "$NGINX_ENABLED"
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable --now home-cloud
nginx -t
systemctl restart nginx

echo "[7/7] Starting Tailscale service"
systemctl enable --now tailscaled

echo
echo "Deployment files are in place."
echo "Run the command below to join your tailnet:"
echo "  sudo tailscale up"
echo
echo "Useful checks:"
echo "  systemctl status home-cloud --no-pager"
echo "  systemctl status nginx --no-pager"
echo "  curl -I http://127.0.0.1/healthz"
echo "  tailscale ip -4"
