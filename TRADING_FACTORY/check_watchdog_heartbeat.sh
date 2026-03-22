#!/bin/bash
# check_watchdog_heartbeat.sh — Monitors the SYSTEM_WATCHDOG itself
# Cron: */30 * * * * (every 30 min, offset from watchdog's */15)
# If the heartbeat file is older than 45 min, the watchdog is dead.

set -euo pipefail

HEARTBEAT_FILE="/home/openclawadmin/openclaw/workspace/state/watchdog_heartbeat"
MAX_AGE_SECONDS=2700  # 45 minutes (3 missed runs)
LOG_FILE="/home/openclawadmin/logs/watchdog_meta.log"

now=$(date +%s)

if [ ! -f "$HEARTBEAT_FILE" ]; then
  echo "[META-WATCHDOG] $(date -u +%Y-%m-%dT%H:%M:%SZ) CRIT — heartbeat file missing: $HEARTBEAT_FILE" >> "$LOG_FILE"
  exit 1
fi

file_mtime=$(stat -c %Y "$HEARTBEAT_FILE")
age=$((now - file_mtime))

if [ "$age" -gt "$MAX_AGE_SECONDS" ]; then
  age_min=$((age / 60))
  echo "[META-WATCHDOG] $(date -u +%Y-%m-%dT%H:%M:%SZ) CRIT — SYSTEM_WATCHDOG stale (last heartbeat ${age_min}m ago, threshold 45m)" >> "$LOG_FILE"
  exit 1
else
  echo "[META-WATCHDOG] $(date -u +%Y-%m-%dT%H:%M:%SZ) OK — heartbeat age ${age}s" >> "$LOG_FILE"
fi
