#!/bin/bash
# Railway startup script for the hermes-auto-parts profile.
# Railway's startCommand replaces the Docker ENTRYPOINT, so this script
# handles everything: venv activation, profile bootstrap, dashboard, gateway.
set -e

source /opt/hermes/.venv/bin/activate

# Bootstrap profile config
bash /opt/hermes/docker/auto-parts-entrypoint.sh

# Start the Hermes dashboard on Railway's assigned port so the web UI
# is accessible at the public Railway URL.
DASH_PORT="${HERMES_DASHBOARD_PORT:-${PORT:-9119}}"
echo "[railway] Starting dashboard on port $DASH_PORT"
hermes dashboard --host 0.0.0.0 --port "$DASH_PORT" --no-open --insecure &
DASH_PID=$!
echo "[railway] Dashboard PID $DASH_PID"

# Start the gateway as the main process.
echo "[railway] Starting gateway"
exec hermes gateway run
