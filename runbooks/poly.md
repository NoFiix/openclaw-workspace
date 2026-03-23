# runbooks/poly.md — Opérations POLY_FACTORY

---

## VÉRIFIER L'ÉTAT DU SYSTÈME

```bash
# État PM2
pm2 show poly-orchestrator | grep -E "status|cpu|memory|restart"

# Logs récents
pm2 logs poly-orchestrator --lines 30

# Positions ouvertes
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/portfolio_state.json \
  | python3 -m json.tool

# Capital et P&L par stratégie
for f in ~/openclaw/workspace/POLY_FACTORY/state/accounts/ACC_POLY_*.json; do
  echo "=== $(basename $f) ==="
  cat "$f" | python3 -c "
import json, sys
d = json.load(sys.stdin)
cap = d.get('capital', {})
print(f'  initial={cap.get(\"initial\")} current={cap.get(\"current\")}')
trades = d.get('trades', [])
open_t = [t for t in trades if t.get('status') == 'open']
print(f'  trades={len(trades)} open={len(open_t)}')
"
done

# Risque global
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/global_risk_state.json \
  | python3 -m json.tool

# Kill switch par stratégie
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/kill_switch_status.json \
  | python3 -m json.tool
```

---

## REDÉMARRER L'ORCHESTRATEUR

```bash
pm2 delete poly-orchestrator && pm2 start ecosystem.config.cjs && pm2 save

# Attendre 30s et vérifier
sleep 30
pm2 logs poly-orchestrator --lines 20 \
  | grep -iE 'trade:signal|error|started|cycle'
```

---

## DIAGNOSTIQUER 0 TRADE

```bash
# 1. Orchestrateur tourne ?
pm2 show poly-orchestrator | grep status

# 2. Bus pub/sub fonctionnel ?
# Vérifier que signal:resolution_parsed circule
pm2 logs poly-orchestrator --lines 50 \
  | grep -iE 'resolution_parsed|trade:signal|opp_scorer|no_scanner'

# 3. Agents actifs ?
cat ~/openclaw/workspace/POLY_FACTORY/state/orchestrator/heartbeat_state.json \
  | python3 -m json.tool | grep -E 'status|disabled'

# 4. Kill switch global déclenché ?
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/global_risk_state.json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('STATUS:', d.get('status'))"

# 5. NO_SCANNER stopped ?
cat ~/openclaw/workspace/POLY_FACTORY/state/orchestrator/strategy_registry.json \
  | python3 -m json.tool | grep -A2 'NO_SCANNER'
cat ~/openclaw/workspace/POLY_FACTORY/state/orchestrator/strategy_lifecycle.json \
  | python3 -m json.tool | grep -A2 'NO_SCANNER'

# 6. Vrais events en attente (pas l'historique)
python3 -c "
import json
pending_file = '/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/bus/pending_events.jsonl'
processed_file = '/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/bus/processed_events.jsonl'
try:
    with open(pending_file) as f:
        total = sum(1 for _ in f)
    with open(processed_file) as f:
        processed = sum(1 for _ in f)
    print(f'Total events: {total}')
    print(f'Processed: {processed}')
    print(f'Real pending: {max(0, total - processed)}')
except Exception as e:
    print(f'Erreur: {e}')
"
```

---

## RESET NO_SCANNER APRÈS KILL SWITCH

```bash
# Remettre NO_SCANNER en paper_testing
python3 -c "
import json

# Registry
reg_path = '/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/orchestrator/strategy_registry.json'
with open(reg_path) as f:
    reg = json.load(f)
if 'POLY_NO_SCANNER' in reg:
    reg['POLY_NO_SCANNER']['status'] = 'paper_testing'
    with open(reg_path, 'w') as f:
        json.dump(reg, f, indent=2)
    print('Registry OK')

# Lifecycle
lc_path = '/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/orchestrator/strategy_lifecycle.json'
with open(lc_path) as f:
    lc = json.load(f)
if 'POLY_NO_SCANNER' in lc:
    lc['POLY_NO_SCANNER']['lifecycle_phase'] = 'paper'
    with open(lc_path, 'w') as f:
        json.dump(lc, f, indent=2)
    print('Lifecycle OK')
"

# Redémarrer pour prendre en compte
pm2 delete poly-orchestrator && pm2 start ecosystem.config.cjs && pm2 save
```

---

## VÉRIFIER LA RAM ET LE CPU

```bash
pm2 show poly-orchestrator | grep -E "cpu|memory"

# Si RAM > 1 Go → vérifier la rétention bus
python3 -c "
import os
bus_dir = '/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/bus/'
if os.path.exists(bus_dir):
    for f in sorted(os.listdir(bus_dir)):
        path = os.path.join(bus_dir, f)
        size = os.path.getsize(path) / 1024 / 1024
        lines = sum(1 for _ in open(path, 'rb'))
        print(f'{size:.1f} MB | {lines} lignes | {f}')
"
```

**Si RAM > 1.5 Go :** la fenêtre de rétention bus est peut-être trop longue.
Vérifier `compact(max_age_hours=...)` dans `core/poly_event_bus.py`.
Seuil recommandé : 1h (voir DEC-017).
