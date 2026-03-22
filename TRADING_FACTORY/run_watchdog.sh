#!/bin/bash
set -euo pipefail

CONTAINER="openclaw-openclaw-gateway-1"
STATE_DIR="/home/node/.openclaw/workspace/state/trading"
WORKSPACE_DIR="/home/node/.openclaw/workspace"
SKILL_PATH="${WORKSPACE_DIR}/TRADING_FACTORY/SYSTEM_WATCHDOG/index.js"
RUN_ID="SYSTEM_WATCHDOG-$(date +%s%3N)"
PAYLOAD_PATH="${STATE_DIR}/runs/${RUN_ID}.json"

cleanup() {
  docker exec "$CONTAINER" rm -f "$PAYLOAD_PATH" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "[WATCHDOG] $(date -u +%Y-%m-%dT%H:%M:%SZ) Container not running: $CONTAINER"
  exit 1
fi

docker exec "$CONTAINER" sh -c "
  mkdir -p '${STATE_DIR}/runs' &&
  printf '%s' '{\"agent_id\":\"SYSTEM_WATCHDOG\",\"run_id\":\"${RUN_ID}\",\"state_dir\":\"${STATE_DIR}\",\"workspace_dir\":\"${WORKSPACE_DIR}\"}' > '${PAYLOAD_PATH}'
"

docker exec "$CONTAINER" node --experimental-vm-modules \
  "$SKILL_PATH" --input "$PAYLOAD_PATH"

# Write heartbeat file on successful run (used by check_watchdog_heartbeat.sh)
HEARTBEAT_FILE="/home/openclawadmin/openclaw/workspace/state/watchdog_heartbeat"
date -u +%Y-%m-%dT%H:%M:%SZ > "$HEARTBEAT_FILE"
