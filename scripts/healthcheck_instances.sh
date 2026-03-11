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

failed=0
for i in $(seq 0 $((instance_count - 1))); do
    port=$((base_port + i))
    if ! curl -fsS "http://127.0.0.1:${port}/healthz" >/dev/null; then
        echo "Unhealthy: 127.0.0.1:${port}"
        failed=1
    else
        echo "OK: 127.0.0.1:${port}"
    fi
done

exit "$failed"
