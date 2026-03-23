# runbooks/incidents.md — Gestion des incidents

---

## ARBRE DE DÉCISION — PREMIER DIAGNOSTIC

```
Quelque chose ne va pas ?
    ↓
1. Les pollers tournent ?
   docker exec openclaw-openclaw-gateway-1 sh -c "ps aux | grep poller | grep -v grep"
   pm2 list
    ↓
2. Kill switch déclenché ?
   cat state/trading/exec/killswitch.json | python3 -c "import json,sys; print(json.load(sys.stdin).get('tripped'))"
   cat POLY_FACTORY/state/risk/global_risk_state.json | python3 -c "import json,sys; print(json.load(sys.stdin).get('status'))"
    ↓
3. API Anthropic opérationnelle ?
   → Vérifier les logs pour erreurs 429/500
    ↓
4. Espace disque ?
   df -h ~/openclaw/workspace/
    ↓
5. RAM disponible ?
   free -h
```

---

## INCIDENT : TRADING POLLER CRASHÉ

**Symptôme :** Plus de prix Binance, 0 signal depuis X minutes.

```bash
# Diagnostiquer
docker exec openclaw-openclaw-gateway-1 sh -c "
ps aux | grep 'TRADING_FACTORY/poller' | grep -v grep \
  || echo '❌ Poller arrêté'
tail -30 /home/node/.openclaw/workspace/state/trading/poller.log \
  | grep -iE 'error|crash|FATAL'
"

# Relancer
docker exec -d openclaw-openclaw-gateway-1 sh -c "
node /home/node/.openclaw/workspace/TRADING_FACTORY/poller.js \
  >> /home/node/.openclaw/workspace/state/trading/poller.log 2>&1
"
```

---

## INCIDENT : POLY ORCHESTRATEUR CRASHÉ

**Symptôme :** `pm2 show poly-orchestrator` affiche `errored` ou `stopped`.

```bash
# Diagnostiquer
pm2 logs poly-orchestrator --lines 50 | grep -iE 'error|FATAL|crash'

# Relancer
pm2 delete poly-orchestrator
pm2 start ~/openclaw/workspace/POLY_FACTORY/ecosystem.config.cjs \
  || pm2 start ecosystem.config.cjs --name poly-orchestrator \
       -- python3 run_orchestrator.py
pm2 save
```

---

## INCIDENT : KILL SWITCH TRADING DÉCLENCHÉ

**Symptôme :** Telegram alerte kill switch, 0 nouveaux trades.

```bash
# 1. Identifier la cause
cat ~/openclaw/workspace/state/trading/exec/killswitch.json \
  | python3 -m json.tool

# 2. Vérifier les wallets
for s in MeanReversion Momentum Breakout NewsTrading; do
  echo "=== $s ==="
  cat ~/openclaw/workspace/state/trading/strategies/$s/wallet.json \
    | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(f'  cash={d[\"cash\"]} status={d[\"status\"]} pnl={d[\"realized_pnl\"]}')
"
done

# 3. Reset (uniquement après validation Dan)
# Voir runbooks/trading.md → RESET KILL SWITCH GLOBAL
```

---

## INCIDENT : KILL SWITCH POLY DÉCLENCHÉ

**Symptôme :** Telegram alerte, stratégie en `stopped`.

```bash
# Identifier quelle stratégie
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/kill_switch_status.json \
  | python3 -m json.tool

cat ~/openclaw/workspace/POLY_FACTORY/state/risk/global_risk_state.json \
  | python3 -m json.tool

# Reset stratégie spécifique
# Voir runbooks/poly.md → RESET NO_SCANNER APRÈS KILL SWITCH
# (adapter pour la stratégie concernée)
```

---

## INCIDENT : DASHBOARD INACCESSIBLE

**Symptôme :** Page blanche, erreur connexion, données figées.

```bash
# 1. PM2 status
pm2 show dashboard-api | grep status

# 2. Port 3001 répond ?
curl -s http://localhost:3001/api/health | head -5

# 3. Relancer
pm2 delete dashboard-api
pm2 start ~/openclaw/workspace/dashboard/api/ecosystem.config.cjs
pm2 save

# 4. Si données figées → cache navigateur
# Rebuild : cd dashboard/web && npm run build
```

---

## INCIDENT : RAM CRITIQUE POLY

**Symptôme :** PM2 montre > 1.5 Go RAM pour `poly-orchestrator`.

```bash
# Voir rétention bus
pm2 logs poly-orchestrator --lines 10

# Compacter manuellement le bus
cd ~/openclaw/workspace/POLY_FACTORY
python3 -c "
import sys
sys.path.insert(0, '.')
from core.poly_event_bus import PolyEventBus
bus = PolyEventBus()
bus.compact(max_age_hours=1)
print('Bus compacté')
"

# Relancer l'orchestrateur
pm2 delete poly-orchestrator && pm2 start ecosystem.config.cjs && pm2 save
```

---

## INCIDENT : PUBLICATIONS CONTENT ARRÊTÉES

**Symptôme :** Plus de posts Twitter/Telegram depuis > 12h.

```bash
# Diagnostic rapide
docker exec openclaw-openclaw-gateway-1 sh -c "
ps aux | grep 'CONTENT_FACTORY/poller' | grep -v grep \
  || echo '❌ Poller arrêté'
tail -10 /home/node/.openclaw/workspace/state/content_poller.log
"

# Voir runbooks/content.md → REDÉMARRER LE CONTENT POLLER
```

---

## INCIDENT : API ANTHROPIC DOWN / RATE LIMIT

**Symptôme :** Erreurs 429 ou 500 dans les logs, HOLD à 100%.

```bash
# Vérifier dans les logs trading
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -100 /home/node/.openclaw/workspace/state/trading/poller.log \
  | grep -iE '429|500|rate.limit|overloaded'
"

# Vérifier coûts LLM (surcharge soudaine ?)
tail -10 ~/openclaw/workspace/state/trading/learning/token_costs.jsonl \
  | python3 -c "
import json, sys
for line in sys.stdin:
    try:
        d = json.loads(line)
        print(f\"{d.get('ts','?')} | {d.get('agent','?')} | ${d.get('cost_usd',0):.4f}\")
    except: pass
"
```

**Actions :**
- 429 → attendre, le système reprendra automatiquement
- 500 persistant → vérifier status.anthropic.com
- Coût soudainement élevé → vérifier qu'un agent ne boucle pas

---

## INCIDENT : ESPACE DISQUE FAIBLE

```bash
# État disque global
df -h ~/openclaw/

# Trouver les gros fichiers
du -sh ~/openclaw/workspace/state/trading/bus/*.jsonl 2>/dev/null | sort -rh | head -10
du -sh ~/openclaw/workspace/POLY_FACTORY/state/bus/*.jsonl 2>/dev/null | sort -rh | head -10

# Forcer rotation bus trading
docker exec openclaw-openclaw-gateway-1 node \
  /home/node/.openclaw/workspace/TRADING_FACTORY/bus_cleanup_trading.js

# Compacter bus POLY
cd ~/openclaw/workspace/POLY_FACTORY && python3 -c "
from core.poly_event_bus import PolyEventBus
bus = PolyEventBus()
bus.compact(max_age_hours=1)
print('OK')
"
```
