#!/bin/bash
CONTAINER="openclaw-openclaw-gateway-1"
POLLER_PATH="/home/node/.openclaw/workspace/TRADING_FACTORY/poller.js"

echo "[restart_poller] 🔍 Pollers actifs avant restart :"
docker exec $CONTAINER ps aux | grep "trading/poller" | grep -v grep

# Tuer via pkill (matche le chemin complet)
docker exec $CONTAINER pkill -f "trading/poller.js" 2>/dev/null
echo "[restart_poller] Signal envoyé"
sleep 3

# Vérifier qu'ils sont bien morts
REMAINING=$(docker exec $CONTAINER ps aux | grep "trading/poller" | grep -v grep | wc -l)
echo "[restart_poller] Pollers restants après kill: $REMAINING"

# Relancer un seul — stdout/stderr redirigés vers poller.log
LOG_PATH="/home/node/.openclaw/workspace/state/trading/poller.log"
docker exec -d $CONTAINER sh -c "node $POLLER_PATH >> $LOG_PATH 2>&1"
sleep 2

# Vérification finale
COUNT=$(docker exec $CONTAINER ps aux | grep "trading/poller" | grep -v grep | wc -l)
echo "[restart_poller] ✅ $COUNT trading poller(s) actif(s) après restart"
docker exec $CONTAINER ps aux | grep "trading/poller" | grep -v grep
