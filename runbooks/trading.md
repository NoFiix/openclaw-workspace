# runbooks/trading.md — Opérations TRADING_FACTORY

---

## DÉMARRER LE TRADING POLLER

```bash
# Vérifier s'il tourne déjà
docker exec openclaw-openclaw-gateway-1 sh -c "
ps aux | grep 'TRADING_FACTORY/poller' | grep -v grep
"

# Lancer
docker exec -d openclaw-openclaw-gateway-1 sh -c "
node /home/node/.openclaw/workspace/TRADING_FACTORY/poller.js \
  >> /home/node/.openclaw/workspace/state/trading/poller.log 2>&1
"

# Vérifier après 10s
sleep 10
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -20 /home/node/.openclaw/workspace/state/trading/poller.log \
  | grep -iE 'BINANCE|MARKET_EYE|error'
"
```

---

## ARRÊTER LE TRADING POLLER

```bash
docker exec openclaw-openclaw-gateway-1 sh -c "
pkill -f 'TRADING_FACTORY/poller.js' && echo 'Arrêté' || echo 'Déjà arrêté'
"
```

---

## VÉRIFIER L'ÉTAT DU SYSTÈME

```bash
# Agents actifs
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -100 /home/node/.openclaw/workspace/state/trading/poller.log \
  | grep -iE '^\[.*\]\[20' | awk '{print \$1}' | sort | uniq -c | sort -rn | head -20
"

# Prix Binance en temps réel
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -20 /home/node/.openclaw/workspace/state/trading/poller.log \
  | grep 'price='
"

# Kill switch état
cat ~/openclaw/workspace/state/trading/exec/killswitch.json \
  | python3 -m json.tool

# Wallets des 4 stratégies
for s in MeanReversion Momentum Breakout NewsTrading; do
  echo "=== $s ==="
  cat ~/openclaw/workspace/state/trading/strategies/$s/wallet.json \
    | python3 -m json.tool | grep -E "cash|status|realized_pnl|trade_count"
done

# Positions ouvertes
cat ~/openclaw/workspace/state/trading/exec/positions_testnet.json \
  | python3 -m json.tool
```

---

## RESET CIRCUIT BREAKER (stratégie suspendue)

```bash
# Identifier la stratégie suspendue
for s in MeanReversion Momentum Breakout NewsTrading; do
  status=$(cat ~/openclaw/workspace/state/trading/strategies/$s/wallet.json \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','?'))")
  echo "$s : $status"
done

# Reset manuel du wallet (remplacer STRATEGIE par le nom exact)
# Faire depuis l'utilisateur ubuntu (droits fichier)
python3 -c "
import json
path = '/home/openclawadmin/openclaw/workspace/state/trading/strategies/STRATEGIE/wallet.json'
with open(path) as f:
    w = json.load(f)
w['cash'] = w['initial_capital']
w['allocated'] = 0
w['status'] = 'active'
w['suspended_reason'] = None
from datetime import datetime, timezone
w['updated_at'] = datetime.now(timezone.utc).isoformat()
with open(path, 'w') as f:
    json.dump(w, f, indent=2)
print('Reset OK:', path)
"
```

---

## RESET KILL SWITCH GLOBAL

```bash
# Voir l'état actuel
cat ~/openclaw/workspace/state/trading/exec/killswitch.json \
  | python3 -m json.tool

# Reset manuel (uniquement après validation Dan)
python3 -c "
import json
from datetime import datetime, timezone
path = '/home/openclawadmin/openclaw/workspace/state/trading/exec/killswitch.json'
with open(path) as f:
    ks = json.load(f)
ks['state'] = 'ACTIVE'
ks['tripped'] = False
ks['reset_at'] = datetime.now(timezone.utc).isoformat()
with open(path, 'w') as f:
    json.dump(ks, f, indent=2)
print('Kill switch reset')
"
```

---

## DIAGNOSTIQUER 0 SIGNAL / 0 TRADE

```bash
# 1. Le poller tourne ?
docker exec openclaw-openclaw-gateway-1 sh -c "
ps aux | grep 'TRADING_FACTORY/poller' | grep -v grep
"

# 2. Prix Binance reçus ?
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -50 /home/node/.openclaw/workspace/state/trading/poller.log \
  | grep 'BTCUSDT' | tail -3
"

# 3. Régime détecté ?
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -100 /home/node/.openclaw/workspace/state/trading/poller.log \
  | grep 'REGIME\|regime' | tail -5
"

# 4. hasSignal() passe ?
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -100 /home/node/.openclaw/workspace/state/trading/poller.log \
  | grep -iE 'hasSignal|skip|signal|génération' | tail -10
"

# 5. Kill switch déclenché ?
cat ~/openclaw/workspace/state/trading/exec/killswitch.json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('TRIPPED:', d.get('tripped', False))"

# 6. API Anthropic opérationnelle ?
docker exec openclaw-openclaw-gateway-1 node -e "
const https = require('https');
const req = https.request({
  hostname: 'api.anthropic.com',
  path: '/v1/messages',
  method: 'POST',
  headers: {
    'x-api-key': process.env.ANTHROPIC_API_KEY,
    'anthropic-version': '2023-06-01',
    'content-type': 'application/json'
  }
}, res => {
  let data = '';
  res.on('data', d => data += d);
  res.on('end', () => console.log('STATUS:', res.statusCode));
});
req.write(JSON.stringify({model:'claude-haiku-4-5-20251001',max_tokens:10,messages:[{role:'user',content:'ping'}]}));
req.end();
"
```

---

## DÉCLENCHER STRATEGY_SCOUT MANUELLEMENT

```bash
docker exec openclaw-openclaw-gateway-1 sh -c "
echo '{\"agent_id\":\"STRATEGY_SCOUT\",\"run_id\":\"MANUAL_TEST\",
  \"state_dir\":\"/home/node/.openclaw/workspace/state/trading\",
  \"workspace_dir\":\"/home/node/.openclaw/workspace\"}' \
  > /home/node/.openclaw/workspace/state/trading/runs/manual_scout.json && \
node --experimental-vm-modules \
  /home/node/.openclaw/workspace/TRADING_FACTORY/STRATEGY_SCOUT/index.js \
  --input /home/node/.openclaw/workspace/state/trading/runs/manual_scout.json
"
```

---

## VALIDER UNE CANDIDATE STRATÉGIE

```bash
# Voir les candidates en attente
cat ~/openclaw/workspace/state/trading/configs/candidates_pending.json \
  | python3 -m json.tool | grep -E 'candidate_id|candidate_seq|status|strategy_name'

# Modifier manuellement le statut (depuis ubuntu)
# Ouvrir le fichier et changer status en :
#   approved_config_ready   → sera ajoutée au registry
#   approved_dev_required   → validée mais dev nécessaire
#   rejected                → rejetée
nano ~/openclaw/workspace/state/trading/configs/candidates_pending.json
```
