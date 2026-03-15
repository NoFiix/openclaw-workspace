#!/bin/bash
# setup_ufw.sh — Configure UFW firewall for OpenClaw VPS
# REQUIRES: sudo access (run as root or with sudo)
# Usage: sudo bash setup_ufw.sh
#
# Rules:
#   - Allow SSH (22)
#   - Allow HTTP (80) and HTTPS (443)
#   - Block everything else (including Docker ports 18789/18790)

set -euo pipefail

echo "[UFW] Configuring firewall rules..."

# Reset to defaults
ufw --force reset

# Default policies: deny incoming, allow outgoing
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (critical — don't lock yourself out)
ufw allow 22/tcp comment 'SSH'

# Allow HTTP and HTTPS
ufw allow 80/tcp comment 'HTTP nginx'
ufw allow 443/tcp comment 'HTTPS future'

# Enable UFW (non-interactive)
ufw --force enable

# Show status
ufw status verbose

echo ""
echo "[UFW] Firewall configured. Ports 18789/18790 are now blocked."
echo "[UFW] NOTE: Docker may bypass UFW via iptables. If ports 18789/18790"
echo "[UFW] are still accessible, add to /etc/docker/daemon.json:"
echo '  { "iptables": false }'
echo "[UFW] or bind those ports to 127.0.0.1 in docker-compose.yml."
