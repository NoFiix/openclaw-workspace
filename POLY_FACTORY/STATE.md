# POLY_FACTORY/STATE.md — Sources de vérité

> Dernière mise à jour : Mars 2026
> Ce fichier liste tous les fichiers d'état de POLY_FACTORY,
> leur rôle, qui les écrit, qui les lit, et s'ils sont source de vérité.

---

## RÈGLE FONDAMENTALE

`POLY_FACTORY/state/` ne bouge jamais.
Toute donnée affichée dans le dashboard doit être tracée à un fichier de cette liste.

---

## STRUCTURE COMPLÈTE

```
POLY_FACTORY/state/
├── accounts/           ← capital et P&L par stratégie (SOURCE DE VÉRITÉ)
├── risk/               ← kill switch et état risque global
├── orchestrator/       ← état système et heartbeats
├── evaluation/         ← scores stratégies
├── llm/                ← tracking coûts LLM
├── bus/                ← events JSONL (append-only)
├── feeds/              ← prix marchés Polymarket
├── historical/         ← données historiques
├── audit/              ← append-only, jamais purgé
└── trading/            ← trades paper log
```

---

## FICHIERS D'ÉTAT CRITIQUES

### Comptes — source de vérité capital et P&L

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `accounts/ACC_POLY_*.json` | POLY_PAPER_ENGINE, POLY_CAPITAL_MANAGER | Dashboard, RISK_GUARDIAN | ✅ OUI |

**Structure ACC_POLY_*.json :**
```json
{
  "strategy_id": "POLY_OPP_SCORER",
  "capital": {
    "initial": 1000,
    "current": 940.78,
    "currency": "EUR"
  },
  "pnl": {
    "total": -59.22,
    "daily": 0
  },
  "trades": [...],
  "drawdown": {...}
}
```

**⚠️ Règles critiques (DEC-015, DEC-016) :**
- `capital.initial` = source de vérité du capital de référence (pas `current`)
- `capital.current` = capital après déduction des trades ouverts par l'orchestrateur
- `pnl.total` ≠ P&L réalisé — représente le coût d'achat des positions ouvertes
- P&L réalisé = reconstruction depuis trades avec `status: resolved` uniquement
- Capital disponible = `capital.initial` - `committed_from_positions` (jamais `current - committed`)

---

### Positions ouvertes — source de vérité

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `risk/portfolio_state.json` | POLY_RISK_GUARDIAN | Dashboard, Stratégies | ✅ OUI — positions ouvertes |

**Structure portfolio_state.json :**
```json
{
  "open_positions": [
    {
      "strategy_id": "POLY_OPP_SCORER",
      "market_id": "0xd8c3...",
      "value_usd": 59.10,
      "direction": "YES",
      "opened_at": "..."
    }
  ]
}
```

**Capital disponible correct :**
```python
committed = sum(p.value_usd for p in portfolio_state.open_positions)
available = acc.capital.initial - committed  # PAS current - committed
```

---

### Risque global

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `risk/global_risk_state.json` | POLY_GLOBAL_RISK_GUARD | Dashboard, SYSTEM_WATCHDOG | ✅ OUI |
| `risk/kill_switch_status.json` | POLY_KILL_SWITCH | Dashboard, Stratégies | ✅ OUI |

**Statuts global_risk_state :**
`NORMAL` → `ALERTE` → `CRITIQUE` → `ARRET_TOTAL`

**Seuils kill switch :**
- Par stratégie : -5% daily, -30% total
- Global : pertes cumulées ≥ 4 000€ → ARRET_TOTAL

---

### Orchestrateur

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `orchestrator/system_state.json` | Orchestrateur Python | Dashboard, SYSTEM_WATCHDOG | ✅ OUI — état global |
| `orchestrator/heartbeat_state.json` | Agents (heartbeat) | POLY_SYSTEM_MONITOR | ✅ OUI — liveness agents |
| `orchestrator/strategy_lifecycle.json` | Orchestrateur | Stratégies | ✅ OUI — lifecycle stratégies |
| `orchestrator/strategy_registry.json` | Orchestrateur | Stratégies, Router | ✅ OUI — registry stratégies |

**⚠️ Après tout incident kill switch :** vérifier BOTH
`strategy_registry.json` ET `strategy_lifecycle.json` —
les deux peuvent avoir des statuts `stopped` à reset manuellement.

---

### Évaluation

| Fichier | Écrit par | Lu par | Nature |
|---------|-----------|--------|--------|
| `evaluation/strategy_scores.json` | POLY_STRATEGY_EVALUATOR | POLY_PROMOTION_GATE, Dashboard | Dérivé (calculé) |

Score sur 8 axes par stratégie. Utilisé par la promotion gate.

---

### Trades paper

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `trading/paper_trades_log.jsonl` | POLY_PAPER_ENGINE | POLY_STRATEGY_EVALUATOR | ✅ OUI — historique trades |

**P&L réalisé = filtrer les trades avec `status: resolved` dans ce fichier.**

---

### Coûts LLM

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `llm/token_costs.jsonl` | poly_log_tokens.py (via agents LLM) | GLOBAL_TOKEN_TRACKER | ✅ OUI — coûts LLM POLY |

**Format event :**
```json
{
  "ts": 1710000000000,
  "date": "2026-03-21",
  "agent": "POLY_OPP_SCORER",
  "model": "claude-sonnet-4-6",
  "input": 150,
  "output": 50,
  "cost_usd": 0.0023,
  "system": "polymarket"
}
```

Lu par `GLOBAL_TOKEN_TRACKER` (TRADING_FACTORY) via `POLY_BASE_PATH` env var
pour l'agrégation cross-factory dans le dashboard LLM Costs.

---

### Bus events — topics et fichiers

| Topic | Type | Fichier JSONL | TTL |
|-------|------|--------------|-----|
| `feed:price_update` | overwrite | `bus/feed_price_update.jsonl` | Court |
| `signal:resolution_parsed` | queue | `bus/signal_resolution_parsed.jsonl` | Variable |
| `signal:market_structure` | queue | `bus/signal_market_structure.jsonl` | Variable |
| `signal:binance_score` | queue | `bus/signal_binance_score.jsonl` | Variable |
| `feed:noaa_update` | queue | `bus/feed_noaa_update.jsonl` | Variable |
| `feed:wallet_update` | queue | `bus/feed_wallet_update.jsonl` | Variable |
| `trade:signal` | queue | `bus/trade_signal.jsonl` | Variable |
| `execute:paper` | queue | `bus/execute_paper.jsonl` | Variable |
| `trade:paper_executed` | queue | `bus/trade_paper_executed.jsonl` | Variable |
| `risk:kill_switch` | priority | `bus/risk_kill_switch.jsonl` | Permanent |
| `system:agent_disabled` | priority | `bus/system_agent_disabled.jsonl` | Variable |
| `news:high_impact` | queue | ⚠️ pas de producteur | — |

**Rétention bus :** `compact(max_age_hours=1)`
Fenêtre 1h = 4x la marge du consumer le plus lent (mkt_analyst, 15 min).

**⚠️ Bus `pending_events.jsonl` et `processed_events.jsonl` :**
Ces fichiers sont des **logs cumulatifs historiques**, pas des queues bloquées.
`bus_pending_real = max(0, total_events - processed_events)` = vrais messages en attente.
Une valeur de 100k+ lignes est normale et attendue.

---

### Feeds

| Fichier | Écrit par | Rôle |
|---------|-----------|------|
| `feeds/polymarket_prices.json` | POLY_MARKET_CONNECTOR | Prix YES/NO temps réel |

---

## HIÉRARCHIE DES SOURCES — POLY

Pour une même métrique, priorité décroissante :

1. `accounts/ACC_POLY_*.json` → `capital.initial` (capital de référence)
2. `risk/portfolio_state.json` → positions ouvertes (capital engagé)
3. `trading/paper_trades_log.jsonl` → P&L réalisé (trades `status: resolved`)
4. `risk/global_risk_state.json` → état risque global
5. `evaluation/strategy_scores.json` → scores (dérivé)
6. `llm/token_costs.jsonl` → coûts LLM bruts
7. Logs PM2 → debug uniquement, jamais source de vérité

---

## CALCULS CORRECTS — RÉFÉRENCE RAPIDE

```python
# Capital disponible par stratégie
committed = sum(p.value_usd for p in portfolio_state.open_positions
                if p.strategy_id == strategy_id)
available = acc.capital.initial - committed

# P&L réalisé (pas pnl.total !)
realized_pnl = sum(t.pnl_eur for t in paper_trades_log
                   if t.strategy_id == strategy_id
                   and t.status == "resolved")

# Capital total dashboard
total_capital = sum(acc.capital.initial for acc in all_accounts)  # = 9000€
total_committed = sum(p.value_usd for p in portfolio_state.open_positions)
total_available = total_capital - total_committed
```
