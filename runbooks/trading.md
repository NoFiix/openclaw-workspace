# runbooks/trading.md

## DÉMARRER / ARRÊTER LE POLLER

```bash
# Vérifier
docker exec openclaw-openclaw-gateway-1 sh -c "ps aux | grep 'TRADING_FACTORY/poller' | grep -v grep"

# Lancer
docker exec -d openclaw-openclaw-gateway-1 sh -c "
node /home/node/.openclaw/workspace/TRADING_FACTORY/poller.js \
  >> /home/node/.openclaw/workspace/state/trading/poller.log 2>&1"

# Arrêter
docker exec openclaw-openclaw-gateway-1 sh -c "pkill -f 'TRADING_FACTORY/poller.js'"
```

## ÉTAT DU SYSTÈME

```bash
# Kill switch
cat ~/openclaw/workspace/state/trading/exec/killswitch.json | python3 -m json.tool

# Wallets
for s in MeanReversion Momentum Breakout NewsTrading; do
  echo "=== $s ==="
  cat ~/openclaw/workspace/state/trading/strategies/$s/wallet.json \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'cash={d[\"cash\"]} status={d[\"status\"]} trades={d[\"trade_count\"]}')"
done

# Positions / Ranking
cat ~/openclaw/workspace/state/trading/exec/positions_testnet.json | python3 -m json.tool
cat ~/openclaw/workspace/state/trading/learning/strategy_ranking.json | python3 -m json.tool

# Logs
docker exec openclaw-openclaw-gateway-1 sh -c "tail -30 /home/node/.openclaw/workspace/state/trading/poller.log"
```

## RESET WALLET SUSPENDU

```bash
# Identifier
for s in MeanReversion Momentum Breakout NewsTrading; do
  python3 -c "import json; d=json.load(open('/home/openclawadmin/openclaw/workspace/state/trading/strategies/$s/wallet.json')); print('$s:', d['status'])"
done

# Reset (remplacer STRATEGIE)
python3 -c "
import json
from datetime import datetime, timezone
path = '/home/openclawadmin/openclaw/workspace/state/trading/strategies/STRATEGIE/wallet.json'
w = json.load(open(path))
w.update({'cash': w['initial_capital'], 'allocated': 0, 'status': 'active', 'suspended_reason': None, 'updated_at': datetime.now(timezone.utc).isoformat()})
json.dump(w, open(path,'w'), indent=2)
print('Reset OK')
"
```

## RESET KILL SWITCH GLOBAL

```bash
python3 -c "
import json
from datetime import datetime, timezone
path = '/home/openclawadmin/openclaw/workspace/state/trading/exec/killswitch.json'
ks = json.load(open(path))
ks.update({'state': 'ACTIVE', 'tripped': False, 'reset_at': datetime.now(timezone.utc).isoformat()})
json.dump(ks, open(path,'w'), indent=2)
print('Kill switch reset')
"
```

## DIAGNOSTIQUER 0 SIGNAL

```bash
# 1. Poller actif ?
docker exec openclaw-openclaw-gateway-1 sh -c "ps aux | grep 'TRADING_FACTORY/poller' | grep -v grep"
# 2. Prix reçus ?
docker exec openclaw-openclaw-gateway-1 sh -c "tail -50 /home/node/.openclaw/workspace/state/trading/poller.log | grep 'BTCUSDT' | tail -3"
# 3. Régime ?
docker exec openclaw-openclaw-gateway-1 sh -c "tail -100 /home/node/.openclaw/workspace/state/trading/poller.log | grep -i 'regime' | tail -5"
# 4. hasSignal ?
docker exec openclaw-openclaw-gateway-1 sh -c "tail -100 /home/node/.openclaw/workspace/state/trading/poller.log | grep -iE 'hasSignal|skip|signal' | tail -10"
# 5. Kill switch ?
cat ~/openclaw/workspace/state/trading/exec/killswitch.json | python3 -c "import json,sys; print('TRIPPED:', json.load(sys.stdin).get('tripped'))"
```

## VALIDER UNE CANDIDATE

```bash
cat ~/openclaw/workspace/state/trading/configs/candidates_pending.json | python3 -m json.tool
# Modifier status : approved_config_ready | approved_dev_required | rejected
nano ~/openclaw/workspace/state/trading/configs/candidates_pending.json
```
