# runbooks/poly.md

## ÉTAT DU SYSTÈME

```bash
pm2 show poly-orchestrator | grep -E "status|cpu|memory|restart"
pm2 logs poly-orchestrator --lines 30

# Positions et capital
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/portfolio_state.json | python3 -m json.tool
for f in ~/openclaw/workspace/POLY_FACTORY/state/accounts/ACC_POLY_*.json; do
  echo "=== $(basename $f .json) ==="
  python3 -c "import json; d=json.load(open('$f')); cap=d.get('capital',{}); t=d.get('trades',[]); print(f'  initial={cap.get(\"initial\")} open={len([x for x in t if x.get(\"status\")==\"open\"])} resolved={len([x for x in t if x.get(\"status\")==\"resolved\"])}')"
done

# Risque
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/global_risk_state.json | python3 -m json.tool
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/kill_switch_status.json | python3 -m json.tool
```

## REDÉMARRER L'ORCHESTRATEUR

```bash
pm2 delete poly-orchestrator && pm2 start ecosystem.config.cjs && pm2 save
```

## DIAGNOSTIQUER 0 TRADE

```bash
# 1. Status
pm2 show poly-orchestrator | grep status
# 2. Bus circulant ?
pm2 logs poly-orchestrator --lines 50 | grep -iE 'resolution_parsed|trade:signal'
# 3. Agents actifs ?
cat ~/openclaw/workspace/POLY_FACTORY/state/orchestrator/heartbeat_state.json | python3 -m json.tool | grep -E 'status|disabled'
# 4. Kill switch global ?
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/global_risk_state.json | python3 -c "import json,sys; print('STATUS:', json.load(sys.stdin).get('status'))"
# 5. Stratégie stopped ?
cat ~/openclaw/workspace/POLY_FACTORY/state/orchestrator/strategy_registry.json | python3 -m json.tool | grep -A2 'NO_SCANNER'
cat ~/openclaw/workspace/POLY_FACTORY/state/orchestrator/strategy_lifecycle.json | python3 -m json.tool | grep -A2 'NO_SCANNER'
# 6. Vrais events en attente
python3 -c "
t=sum(1 for _ in open('/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/bus/pending_events.jsonl'))
p=sum(1 for _ in open('/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/bus/processed_events.jsonl'))
print(f'Total={t} Processed={p} Pending={max(0,t-p)}')"
```

## RESET STRATÉGIE APRÈS KILL SWITCH

```bash
python3 -c "
import json
for path, key in [
  ('/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/orchestrator/strategy_registry.json', 'status'),
  ('/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/orchestrator/strategy_lifecycle.json', 'lifecycle_phase')
]:
  d = json.load(open(path))
  # Adapter POLY_NO_SCANNER et la valeur selon la stratégie
  if 'POLY_NO_SCANNER' in d:
    d['POLY_NO_SCANNER'][key] = 'paper_testing' if key == 'status' else 'paper'
    json.dump(d, open(path,'w'), indent=2)
    print(f'OK: {path}')
"
pm2 delete poly-orchestrator && pm2 start ecosystem.config.cjs && pm2 save
```

## RAM / CPU ÉLEVÉ

```bash
pm2 show poly-orchestrator | grep -E "cpu|memory"
# Si RAM > 1.5 Go → vérifier compact(max_age_hours=...) dans core/poly_event_bus.py (seuil = 1h)
python3 -c "
import os; bus='/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/bus/'
for f in sorted(os.listdir(bus)):
  p=os.path.join(bus,f); s=os.path.getsize(p)/1024/1024
  print(f'{s:.1f}MB {f}')"
```
