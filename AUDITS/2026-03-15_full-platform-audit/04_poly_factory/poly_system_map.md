# poly_system_map.md — Quick Reference POLY_FACTORY

**Date** : 2026-03-15
**Usage** : Référence rapide pour comprendre le système en < 5 minutes

---

## Diagramme global simplifié

```
                    ┌───────────────────────────────────┐
                    │        EXTERNAL APIS               │
                    │  Polymarket · Binance · NOAA       │
                    │  Anthropic (Sonnet/Haiku)           │
                    └─────────────┬─────────────────────┘
                                  │
               ┌──────────────────┼──────────────────┐
               ▼                  ▼                  ▼
         ┌──────────┐     ┌──────────┐      ┌──────────┐
         │connector │     │ binance  │      │  noaa    │
         │Polymarket│     │  feed    │      │  feed    │
         │ 300s ✅  │     │ 30s ❌   │      │ 120s ✅  │
         └────┬─────┘     └────┬─────┘      └────┬─────┘
              │                │                  │
              ▼                ▼                  │
         ┌──────────┐   ┌──────────┐             │
         │   MSA    │   │ binance  │             │
         │ 30s ❌   │   │ signals  │             │
         │          │   │ 10s ❌   │             │
         └────┬─────┘   └────┬─────┘             │
              │               │                   │
    ┌─────────┼───────────────┼───────────────────┼────────────┐
    │         ▼               ▼                   ▼            │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │              9 STRATÉGIES                           │  │
    │  │                                                     │  │
    │  │  arb_scanner ❌   weather_arb ✅   latency_arb ❌  │  │
    │  │  brownian ❌      pair_cost ❌     opp_scorer ✅   │  │
    │  │  no_scanner ✅    convergence ✅   news_strat ✅   │  │
    │  │                                                     │  │
    │  │  5 actives / 4 disabled → 0 trade:signal            │  │
    │  └───────────────────────┬────────────────────────────┘  │
    │                           │                               │
    │                           ▼                               │
    │  ┌──────────────────────────────────────────────────┐    │
    │  │  ORCHESTRATEUR — 7 FILTRES                        │    │
    │  │  1.quality 2.micro 3.resolution 4.kelly           │    │
    │  │  5.kill_switch 6.risk_guardian 7.capital           │    │
    │  └───────────────────────┬──────────────────────────┘    │
    │                           │                               │
    │                           ▼                               │
    │  ┌──────────────────┐  ┌──────────────────────────┐     │
    │  │ exec_router ❌   │→ │ paper_engine ✅           │     │
    │  │ (DISABLED)       │  │ slippage + fees 0.2%     │     │
    │  └──────────────────┘  │ → paper_trades_log.jsonl │     │
    │                         └──────────────────────────┘     │
    │                                                           │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │  RISK LAYER                                         │  │
    │  │  kill_switch (per strategy) · risk_guardian (port.) │  │
    │  │  global_risk_guard (-4000€ → ARRÊT TOTAL)          │  │
    │  └────────────────────────────────────────────────────┘  │
    │                                                           │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │  MONITORING                                         │  │
    │  │  heartbeat (300s) · system_monitor (300s)           │  │
    │  │  8 actifs / 11 disabled / 0 trades                  │  │
    │  └────────────────────────────────────────────────────┘  │
    └───────────────────────────────────────────────────────────┘
```

---

## Composants CORE (sans eux = système mort)

| Composant | Rôle | Statut | Sans lui... |
|-----------|------|--------|-------------|
| poly_factory_orchestrator | 7 filtres + routage signaux | ✅ ACTIF (98% CPU) | Aucun signal traité |
| poly_event_bus | Communication inter-agents | ✅ ACTIF (70k backlog) | Agents isolés, 0 flux |
| connector_polymarket | Données marchés Polymarket | ✅ ACTIF | Aucun prix → aucun signal |
| poly_execution_router | Route validated → paper/live | ❌ **DISABLED** | Signaux validés jamais exécutés |
| poly_paper_execution_engine | Exécution paper trades | ✅ ACTIF | Trades validés mais jamais loggés |
| poly_strategy_account | Capital isolé par stratégie | ✅ ACTIF (9 comptes) | Pas de gestion capital |
| poly_kill_switch | Protection -5% daily / -30% total | ✅ ACTIF (non testé) | Pas de protection per-strategy |
| poly_global_risk_guard | Protection -4 000€ globale | ✅ ACTIF (NORMAL) | Pas de protection globale |

**Point critique** : `exec_router` est **DISABLED**. C'est le seul pont entre orchestrateur et paper_engine. Même si un signal passait les 7 filtres, il ne serait jamais exécuté.

---

## État actuel

| Métrique | Valeur | Tag |
|----------|--------|-----|
| Mode | **PAPER TESTING** | [OBSERVÉ] |
| Démarré | 2026-03-14T02:51Z (~1.5 jours) | [OBSERVÉ] |
| Stratégies | 9 (5 actives, 4 disabled) | [OBSERVÉ] |
| Capital total | 9 000€ fictifs | [OBSERVÉ] |
| PnL total | **0€** | [OBSERVÉ] |
| Trades exécutés | **0** | [OBSERVÉ] |
| Agents actifs | 8 / 19 | [OBSERVÉ] |
| Agents disabled | **11** (3+ restarts) | [OBSERVÉ] |
| Bus pending events | **70k** (19 Mo) | [OBSERVÉ] |
| Kill switch global | NORMAL | [OBSERVÉ] |
| CPU orchestrateur | **98%** | [OBSERVÉ] |
| LLM token costs | 0 (fichier vide) | [OBSERVÉ] |
| Marchés suivis | 20 | [OBSERVÉ] |

---

## Top 5 risques résumés

| # | Risque | Sévérité |
|---|--------|----------|
| 1 | 11 agents disabled — pipeline cassé, exec_router mort → 0 trades possibles | **CRITIQUE** |
| 2 | 98% CPU orchestrateur — bus I/O thrashing sur 70k events, dégrade tout le serveur | **ÉLEVÉ** |
| 3 | 0 trades en 1.5j — aucune stratégie n'a trouvé d'edge, seuils peut-être trop stricts | **ÉLEVÉ** |
| 4 | WALLET_PRIVATE_KEY absent — passage live structurellement bloqué | **ÉLEVÉ** |
| 5 | Bus backlog 70k events — croissance ~10 Mo/jour, compaction insuffisante | **ÉLEVÉ** |

---

## Checklist : que vérifier si aucun trade n'est généré

### 1. Vérifier l'état des agents
```bash
cat POLY_FACTORY/state/orchestrator/heartbeat_state.json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for name, info in data['agents'].items():
    status = info.get('status', '?')
    restarts = info.get('restart_count', 0)
    emoji = '✅' if status == 'active' else '❌'
    print(f'{emoji} {name}: {status} (restarts: {restarts})')
"
```
→ Si `exec_router` est disabled, **aucun trade ne sera jamais exécuté**.

### 2. Vérifier le bus
```bash
wc -l POLY_FACTORY/state/bus/pending_events.jsonl
```
→ Si >50k events, forcer une compaction ou redémarrer l'orchestrateur.

### 3. Vérifier si des trade:signal existent
```bash
grep '"trade:signal"' POLY_FACTORY/state/bus/pending_events.jsonl | wc -l
```
→ Si 0, aucune stratégie n'a trouvé d'edge.

### 4. Vérifier les prix Polymarket
```bash
cat POLY_FACTORY/state/feeds/active_markets.json | python3 -c "
import sys, json
markets = json.load(sys.stdin)
for m in markets[:5]:
    print(f'{m.get(\"title\", \"?\")[:50]}: YES={m.get(\"yes_ask\", \"?\")} NO={m.get(\"no_ask\", \"?\")}')"
```
→ Si les prix sont absents ou stale, le connector est cassé.

### 5. Vérifier le kill switch
```bash
cat POLY_FACTORY/state/risk/global_risk_state.json
```
→ Si `status: "ARRET_TOTAL"`, tout est stoppé. Reset manuel requis.

### 6. Vérifier le CPU
```bash
pm2 monit
```
→ Si poly-orchestrator >80% CPU, le bus est saturé. Purger `pending_events.jsonl`.

### 7. Reset les agents disabled
```bash
# Dans Python:
import json
with open('POLY_FACTORY/state/orchestrator/heartbeat_state.json') as f:
    data = json.load(f)
for agent in data['agents'].values():
    agent['restart_count'] = 0
    agent['status'] = 'active'
with open('POLY_FACTORY/state/orchestrator/heartbeat_state.json', 'w') as f:
    json.dump(data, f, indent=2)
# Puis restart: pm2 restart poly-orchestrator
```
