#!/bin/bash
# rotate_poller_log.sh — Rotate trading poller.log
# Cron: 0 4 * * * (daily at 4am UTC)
# Keeps 7 days, compresses old files, rotates if > 50MB or daily

set -euo pipefail

LOG_FILE="/home/openclawadmin/openclaw/workspace/state/trading/poller.log"
MAX_KEEP=7

if [ ! -f "$LOG_FILE" ]; then
  exit 0
fi

# Delete old rotated files beyond MAX_KEEP days
find "$(dirname "$LOG_FILE")" -name "poller.log.*.gz" -mtime +$MAX_KEEP -delete 2>/dev/null || true

# Rotate: rename current → timestamped, compress, truncate
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
ROTATED="${LOG_FILE}.${TIMESTAMP}"

cp "$LOG_FILE" "$ROTATED"
truncate -s 0 "$LOG_FILE"
gzip "$ROTATED"

echo "[ROTATE] $(date -u +%Y-%m-%dT%H:%M:%SZ) Rotated poller.log → poller.log.${TIMESTAMP}.gz" >> /home/openclawadmin/logs/log_rotation.log
