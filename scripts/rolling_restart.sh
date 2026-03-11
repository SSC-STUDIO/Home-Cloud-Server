#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/etc/home-cloud/home-cloud.env"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

instance_count="${LB_INSTANCE_COUNT:-4}"
base_port="${LB_BASE_PORT:-5000}"

for i in $(seq 0 $((instance_count - 1))); do
    port=$((base_port + i))
    echo "Restarting home-cloud@${port}..."
    systemctl restart "home-cloud@${port}"

    for attempt in $(seq 1 10); do
        if curl -fsS "http://127.0.0.1:${port}/healthz" >/dev/null; then
            echo "Healthy: 127.0.0.1:${port}"
            break
        fi
        if [[ "$attempt" -eq 10 ]]; then
            echo "Health check failed for 127.0.0.1:${port}"
            exit 1
        fi
        sleep 1
    done
done

echo "Rolling restart complete."
