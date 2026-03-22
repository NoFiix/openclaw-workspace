#!/bin/sh
# Lance les pollers en background puis démarre le gateway
sleep 5
node /home/node/.openclaw/workspace/TRADING_FACTORY/poller.js >> /home/node/.openclaw/workspace/state/trading/poller.log 2>&1 &
node /home/node/.openclaw/workspace/CONTENT_FACTORY/poller.js >> /home/node/.openclaw/workspace/state/content_poller.log 2>&1 &
exec "$@"
