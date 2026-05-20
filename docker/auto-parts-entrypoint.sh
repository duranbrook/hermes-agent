#!/bin/bash
# Bootstrap the auto-parts profile config into the Railway persistent volume.
# Runs as hermes user (after gosu drop in main entrypoint).
set -e

PROFILE_DIR="${HERMES_HOME:-/opt/data/profiles/auto-parts}"
BUNDLED_DIR="/opt/hermes/docker/profiles/auto-parts"

mkdir -p "$PROFILE_DIR"

# Always refresh config.yaml and SOUL.md from the image.
# The docker entrypoint installs a generic default before this script runs,
# so we must overwrite here to ensure the auto-parts profile is active.
cp "$BUNDLED_DIR/config.yaml" "$PROFILE_DIR/config.yaml"
cp "$BUNDLED_DIR/SOUL.md" "$PROFILE_DIR/SOUL.md"

echo "[auto-parts] Profile bootstrap complete → $PROFILE_DIR"

# Restore WhatsApp session from env var if set and session not already on volume.
# WHATSAPP_CREDS_B64 holds a base64-encoded tar.gz of the Baileys session directory.
WA_SESSION_DIR="$PROFILE_DIR/platforms/whatsapp/session"
if [ -n "$WHATSAPP_CREDS_B64" ] && [ ! -f "$WA_SESSION_DIR/creds.json" ]; then
    echo "[auto-parts] Restoring WhatsApp session from WHATSAPP_CREDS_B64"
    mkdir -p "$WA_SESSION_DIR"
    echo "$WHATSAPP_CREDS_B64" | base64 -d | tar -xz -C "$WA_SESSION_DIR"
    echo "[auto-parts] WhatsApp session restored"
fi

# On Railway, use the assigned PORT for the dashboard so it's publicly reachable.
# HERMES_DASHBOARD_PORT from env takes precedence; fall back to Railway's $PORT.
if [ -n "$PORT" ] && [ -z "$HERMES_DASHBOARD_PORT" ]; then
    export HERMES_DASHBOARD_PORT="$PORT"
fi
