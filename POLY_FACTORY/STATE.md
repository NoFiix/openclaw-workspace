# POLY_FACTORY/STATE.md — Sources de vérité

> ⏸️ SUSPENDU le 2026-04-28 — économie ressources API.
> Pour relancer : `pm2 start poly-orchestrator && pm2 save`

> `POLY_FACTORY/state/` ne bouge jamais. Toute donnée dashboard tracée ici.

---

## FICHIERS CRITIQUES

| Fichier | Écrit par | Vérité | Notes |
|---------|-----------|--------|-------|
| `accounts/ACC_POLY_*.json` | PAPER_ENGINE, CAPITAL_MANAGER | ✅ Capital, P&L | `capital.initial` uniquement, pas `current` |
| `risk/portfolio_state.json` | RISK_GUARDIAN | ✅ Positions ouvertes | Source capital engagé |
| `risk/global_risk_state.json` | GLOBAL_RISK_GUARD | ✅ État risque global | |
| `risk/kill_switch_status.json` | KILL_SWITCH | ✅ KS par stratégie | |
| `orchestrator/strategy_registry.json` | Orchestrateur | ✅ Registry stratégies | ⚠️ après KS : vérifier aussi `strategy_lifecycle.json` |
| `orchestrator/strategy_lifecycle.json` | Orchestrateur | ✅ Lifecycle stratégies | |
| `orchestrator/heartbeat_state.json` | Agents | ✅ Liveness agents | |
| `trading/paper_trades_log.jsonl` | PAPER_ENGINE | ✅ Historique trades | P&L réalisé = filtrer `status:resolved` |
| `llm/token_costs.jsonl` | poly_log_tokens.py | ✅ Coûts LLM bruts | Lu par GLOBAL_TOKEN_TRACKER via POLY_BASE_PATH |
| `evaluation/strategy_scores.json` | STRATEGY_EVALUATOR | Dérivé | |
| `audit/*.jsonl` | Système | Append-only | Jamais purger |

---

## STRUCTURES MINIMALES

**ACC_POLY_*.json** : `capital.initial` | `capital.current` ⚠️ | `pnl.total` ⚠️

**portfolio_state.json** : `open_positions[].strategy_id` | `.value_usd` | `.direction`

**⚠️ `capital.current`** = déductions orchestrateur, ne pas utiliser comme référence
**⚠️ `pnl.total`** = coût d'achat positions ouvertes, pas P&L réalisé

---

## CALCULS CORRECTS

```python
# Capital disponible
available = acc.capital.initial - sum(p.value_usd for p in open_positions if p.strategy_id == sid)

# P&L réalisé
realized = sum(t.pnl_eur for t in paper_trades_log if t.strategy_id == sid and t.status == "resolved")

# Totaux dashboard
total_capital   = sum(acc.capital.initial for acc in all_accounts)  # = 9000€
total_available = total_capital - sum(p.value_usd for p in all_open_positions)
```

---

## BUS EVENTS

| Topic | Producteur → Consommateur | TTL |
|-------|--------------------------|-----|
| `feed:price_update` | CONNECTOR → MARKET_ANALYST | court |
| `signal:resolution_parsed` | MARKET_ANALYST → OPP_SCORER, NO_SCANNER | — |
| `trade:signal` | Stratégies → RISK_GUARDIAN | — |
| `execute:paper` | EXECUTION_ROUTER → PAPER_ENGINE | — |
| `trade:paper_executed` | PAPER_ENGINE → EVALUATOR | — |
| `risk:kill_switch` | RISK_GUARDIAN → Tous | permanent |
| `news:high_impact` | ⚠️ manquant → NEWS_STRAT | — |

Rétention : `compact(max_age_hours=1)`
`pending_events.jsonl` 100k+ lignes = normal (historique cumulatif, pas une queue bloquée)

---

## HIÉRARCHIE DES SOURCES

1. `accounts/ACC_POLY_*.json` → `capital.initial` (référence)
2. `risk/portfolio_state.json` → positions ouvertes
3. `trading/paper_trades_log.jsonl` → P&L réalisé (`status:resolved`)
4. `risk/global_risk_state.json` → risque global
5. `evaluation/strategy_scores.json` → scores (dérivé)
6. `llm/token_costs.jsonl` → coûts LLM
7. Logs PM2 → debug uniquement
