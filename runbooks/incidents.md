# runbooks/incidents.md

## DIAGNOSTIC PREMIER NIVEAU

```bash
# Pollers actifs ?
docker exec openclaw-openclaw-gateway-1 sh -c "ps aux | grep poller | grep -v grep"
pm2 list

# Kill switches
cat ~/openclaw/workspace/state/trading/exec/killswitch.json | python3 -c "import json,sys; print('Trading KS tripped:', json.load(sys.stdin).get('tripped'))"
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/global_risk_state.json | python3 -c "import json,sys; print('Poly status:', json.load(sys.stdin).get('status'))"

# Ressources
df -h ~/openclaw/workspace/ && free -h
```

## TRADING POLLER CRASHÉ

```bash
docker exec openclaw-openclaw-gateway-1 sh -c "tail -20 /home/node/.openclaw/workspace/state/trading/poller.log | grep -iE 'error|FATAL'"
docker exec -d openclaw-openclaw-gateway-1 sh -c "node /home/node/.openclaw/workspace/TRADING_FACTORY/poller.js >> /home/node/.openclaw/workspace/state/trading/poller.log 2>&1"
```

## POLY ORCHESTRATEUR CRASHÉ

```bash
pm2 logs poly-orchestrator --lines 30 | grep -iE 'error|FATAL'
pm2 delete poly-orchestrator && pm2 start ecosystem.config.cjs && pm2 save
```

## KILL SWITCH TRADING DÉCLENCHÉ

```bash
cat ~/openclaw/workspace/state/trading/exec/killswitch.json | python3 -m json.tool
# Wallets
for s in MeanReversion Momentum Breakout NewsTrading; do
  python3 -c "import json; d=json.load(open('/home/openclawadmin/openclaw/workspace/state/trading/strategies/$s/wallet.json')); print('$s: cash=' + str(d['cash']) + ' status=' + d['status'])"
done
# Reset → voir runbooks/trading.md → RESET KILL SWITCH GLOBAL
```

## KILL SWITCH POLY DÉCLENCHÉ

```bash
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/kill_switch_status.json | python3 -m json.tool
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/global_risk_state.json | python3 -m json.tool
# Reset → voir runbooks/poly.md → RESET STRATÉGIE APRÈS KILL SWITCH
```

## DASHBOARD INACCESSIBLE

```bash
pm2 show dashboard-api | grep status
curl -s http://localhost:3001/api/health | head -5
pm2 delete dashboard-api && pm2 start ~/openclaw/workspace/dashboard/api/ecosystem.config.cjs && pm2 save
```

## PUBLICATIONS CONTENT ARRÊTÉES

```bash
docker exec openclaw-openclaw-gateway-1 sh -c "ps aux | grep 'CONTENT_FACTORY/poller' | grep -v grep"
# → voir runbooks/content.md → RELANCER LE POLLER
```

## RAM CRITIQUE POLY

```bash
pm2 show poly-orchestrator | grep memory
# Si > 1.5 Go → vérifier compact(max_age_hours=1) dans core/poly_event_bus.py
cd ~/openclaw/workspace/POLY_FACTORY && python3 -c "
from core.poly_event_bus import PolyEventBus
PolyEventBus().compact(max_age_hours=1)
print('Compacté')"
pm2 delete poly-orchestrator && pm2 start ecosystem.config.cjs && pm2 save
```

## DISQUE PLEIN

```bash
df -h ~/openclaw/
du -sh ~/openclaw/workspace/state/trading/bus/*.jsonl 2>/dev/null | sort -rh | head -5
du -sh ~/openclaw/workspace/POLY_FACTORY/state/bus/*.jsonl 2>/dev/null | sort -rh | head -5
# Forcer rotation Trading
docker exec openclaw-openclaw-gateway-1 node /home/node/.openclaw/workspace/TRADING_FACTORY/bus_cleanup_trading.js
```

## API ANTHROPIC DOWN / RATE LIMIT

```bash
docker exec openclaw-openclaw-gateway-1 sh -c "tail -100 /home/node/.openclaw/workspace/state/trading/poller.log | grep -iE '429|500|rate.limit'"
# 429 → attendre, reprend automatiquement
# 500 persistant → vérifier status.anthropic.com
```
