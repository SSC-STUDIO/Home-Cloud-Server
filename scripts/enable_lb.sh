#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${SUDO_USER:-$USER}"
ENV_FILE="/etc/home-cloud/home-cloud.env"
SYSTEMD_TEMPLATE="$APP_DIR/deploy/systemd/home-cloud@.service.template"
SYSTEMD_UNIT="/etc/systemd/system/home-cloud@.service"
NGINX_SITE="/etc/nginx/sites-available/home-cloud"
NGINX_ENABLED="/etc/nginx/sites-enabled/home-cloud"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run this script with sudo: sudo ./scripts/enable_lb.sh"
    exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

cores="$(nproc 2>/dev/null || echo 2)"
default_instances="$cores"
if [[ "$default_instances" -lt 2 ]]; then
    default_instances=2
fi
max_instances="${LB_MAX_INSTANCES:-8}"
if [[ "$default_instances" -gt "$max_instances" ]]; then
    default_instances="$max_instances"
fi

instance_count="${LB_INSTANCE_COUNT:-$default_instances}"
base_port="${LB_BASE_PORT:-5000}"

echo "Using instance count: $instance_count (base port: $base_port)"

if [[ ! -f "$SYSTEMD_TEMPLATE" ]]; then
    echo "Missing systemd template: $SYSTEMD_TEMPLATE"
    exit 1
fi

python3 - <<PY
from pathlib import Path
service_tpl = Path(r"$SYSTEMD_TEMPLATE").read_text()
service = service_tpl.replace("__APP_DIR__", r"$APP_DIR").replace("__APP_USER__", r"$APP_USER")
Path(r"$SYSTEMD_UNIT").write_text(service)
PY

systemctl daemon-reload

if systemctl list-unit-files | grep -q '^home-cloud\.service'; then
    systemctl disable --now home-cloud || true
fi

for i in $(seq 0 $((instance_count - 1))); do
    port=$((base_port + i))
    systemctl enable --now "home-cloud@${port}"
done

cat > "$NGINX_SITE" <<EOF
upstream home_cloud_upstream {
    least_conn;
EOF

for i in $(seq 0 $((instance_count - 1))); do
    port=$((base_port + i))
    echo "    server 127.0.0.1:${port} max_fails=3 fail_timeout=10s;" >> "$NGINX_SITE"
done

cat >> "$NGINX_SITE" <<'EOF'
}

server {
    listen 80;
    server_name _;

    client_max_body_size 2000M;

    location / {
        proxy_pass http://home_cloud_upstream;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 300;
        proxy_send_timeout 300;
        proxy_next_upstream error timeout http_502 http_503 http_504;
    }

    location = /healthz {
        proxy_pass http://127.0.0.1:5000/healthz;
        access_log off;
    }
}
EOF

ln -sfn "$NGINX_SITE" "$NGINX_ENABLED"
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl restart nginx

echo "Load balancing enabled."
