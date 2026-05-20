#!/bin/bash
# Bootstrap the auto-parts profile config into the Railway persistent volume.
# Runs as hermes user (after gosu drop in main entrypoint).
set -e

PROFILE_DIR="${HERMES_HOME:-/opt/data/profiles/auto-parts}"
BUNDLED_DIR="/opt/hermes/docker/profiles/auto-parts"

mkdir -p "$PROFILE_DIR"

# Copy config.yaml if not already customised on the volume
if [ ! -f "$PROFILE_DIR/config.yaml" ]; then
    echo "[auto-parts] Installing config.yaml"
    cp "$BUNDLED_DIR/config.yaml" "$PROFILE_DIR/config.yaml"
fi

# Always refresh SOUL.md from the image (it's not user-editable)
cp "$BUNDLED_DIR/SOUL.md" "$PROFILE_DIR/SOUL.md"

echo "[auto-parts] Profile bootstrap complete → $PROFILE_DIR"

# On Railway, use the assigned PORT for the dashboard so it's publicly reachable.
# HERMES_DASHBOARD_PORT from env takes precedence; fall back to Railway's $PORT.
if [ -n "$PORT" ] && [ -z "$HERMES_DASHBOARD_PORT" ]; then
    export HERMES_DASHBOARD_PORT="$PORT"
fi
