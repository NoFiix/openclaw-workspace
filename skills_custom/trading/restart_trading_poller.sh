#!/bin/bash
CONTAINER="openclaw-openclaw-gateway-1"
POLLER_PATH="/home/node/.openclaw/workspace/skills_custom/trading/poller.js"

echo "[restart_poller] 🔍 Pollers actifs avant restart :"
docker exec $CONTAINER ps aux | grep "trading/poller" | grep -v grep

# Tuer via pkill (matche le chemin complet)
docker exec $CONTAINER pkill -f "trading/poller.js" 2>/dev/null
echo "[restart_poller] Signal envoyé"
sleep 3

# Vérifier qu'ils sont bien morts
REMAINING=$(docker exec $CONTAINER ps aux | grep "trading/poller" | grep -v grep | wc -l)
echo "[restart_poller] Pollers restants après kill: $REMAINING"

# Relancer un seul
docker exec -d $CONTAINER node $POLLER_PATH
sleep 2

# Vérification finale
COUNT=$(docker exec $CONTAINER ps aux | grep "trading/poller" | grep -v grep | wc -l)
echo "[restart_poller] ✅ $COUNT trading poller(s) actif(s) après restart"
docker exec $CONTAINER ps aux | grep "trading/poller" | grep -v grep
