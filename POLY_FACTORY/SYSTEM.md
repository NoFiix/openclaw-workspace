# POLY_FACTORY/SYSTEM.md

> Paper testing. 50 trades + 14 jours minimum avant promotion live.

---

## STACK

| Composant | Valeur |
|-----------|--------|
| Runtime | Python 3.11 + venv |
| Orchestrateur | PM2 `poly-orchestrator` |
| Bus | `POLY_FACTORY/core/poly_event_bus.py` — JSONL |
| État | `POLY_FACTORY/state/` (JAMAIS DÉPLACER) |
| LLM | Sonnet (analyst, scorer) + Haiku (no_scanner) |

---

## PIPELINE — ORDRE OBLIGATOIRE

```
POLY_MARKET_CONNECTOR → feed:price_update
POLY_DATA_VALIDATOR
POLY_MARKET_ANALYST (Sonnet, cache par market_id) → signal:resolution_parsed
POLY_OPP_SCORER (Sonnet, cache 24h) → trade:signal
POLY_RISK_GUARDIAN (7 filtres déterministes)
POLY_EXECUTION_ROUTER (routing registry paper/live, jamais flag booléen)
POLY_PAPER_ENGINE (jamais py-clob-client) → paper_trades_log.jsonl
POLY_STRATEGY_EVALUATOR (score 8 axes) → strategy_scores.json
POLY_STRATEGY_PROMOTION_GATE → approbation humaine obligatoire
POLY_CAPITAL_MANAGER → live account (après validation uniquement)
```

**Règles absolues :**
- Stratégies → émettent `trade:signal` uniquement, jamais d'exécution directe
- Promotion gate DÉCIDE, Capital Manager EXÉCUTE, jamais automatique

---

## 9 STRATÉGIES (PAPER)

| Stratégie | Type | Trades |
|-----------|------|--------|
| ARB_SCANNER | Dutch Book arbitrage | 0 |
| OPP_SCORER | LLM BUY_YES | actif |
| NO_SCANNER | LLM BUY_NO | actif |
| BROWNIAN_SNIPER | Prix brownien | 0 |
| WEATHER_ARB | Arbitrage météo NOAA | 0 |
| NEWS_STRAT | News high_impact | 0 ⚠️ feed manquant |
| LATENCY_ARB | Latence Binance→Poly | 0 |
| PAIR_COST | Pair trading | 0 |
| CONVERGENCE_STRAT | Convergence wallets | 0 ⚠️ Gamma API 404 |

1 000€ isolés par stratégie. Aucun capital partagé.

---

## AGENTS LLM

| Agent | Modèle | Cache |
|-------|--------|-------|
| POLY_MARKET_ANALYST | claude-sonnet-4-6 | Par market_id |
| POLY_OPP_SCORER | claude-sonnet-4-6 | 24h par market |
| POLY_NO_SCANNER | claude-haiku-4-5-20251001 | Permanent |

Token tracking : `state/llm/token_costs.jsonl` (system="polymarket")

---

## BUS EVENTS

| Topic | Producteur → Consommateur |
|-------|--------------------------|
| `feed:price_update` | CONNECTOR → MARKET_ANALYST |
| `signal:resolution_parsed` | MARKET_ANALYST → OPP_SCORER, NO_SCANNER |
| `trade:signal` | Stratégies → RISK_GUARDIAN |
| `execute:paper` | EXECUTION_ROUTER → PAPER_ENGINE |
| `trade:paper_executed` | PAPER_ENGINE → STRATEGY_EVALUATOR |
| `risk:kill_switch` | RISK_GUARDIAN → Tous |
| `news:high_impact` | ⚠️ MANQUANT → NEWS_STRAT inopérante |

**Bus pub/sub (CRITIQUE — DEC-013) :**
- `_acked_ids` dans `compact()` UNIQUEMENT
- `poll()` filtre via `_consumer_processed[consumer_id]` uniquement
- Ne jamais remettre `_acked_ids` dans `poll()` → casse le multi-consumer (BUG-007, 48h sans trade)

**Rétention :** `compact(max_age_hours=1)` — 4x marge consumer le plus lent (15 min)

---

## RISK MANAGEMENT

| Niveau | Seuil | Fichier |
|--------|-------|---------|
| Kill switch stratégie | -5% daily, -30% total | `risk/kill_switch_status.json` |
| Kill switch global | pertes ≥ 4 000€ → ARRET_TOTAL | `risk/global_risk_state.json` |
| Promotion live | 50 trades + 14j + approbation humaine | — |

Statuts globaux : `NORMAL` → `ALERTE` → `CRITIQUE` → `ARRET_TOTAL`

---

## P&L — RÈGLES CRITIQUES

```
capital.initial    = référence (1000€) — jamais capital.current
capital disponible = capital.initial - somme(positions ouvertes)
P&L réalisé        = trades status:resolved uniquement — jamais pnl.total
```

Position ouverte = capital engagé, pas une perte.

---

## POINTS D'ATTENTION

| Point | Statut |
|-------|--------|
| `news:high_impact` sans producteur | Backlog — NEWS_STRAT inopérante |
| POLY_API_KEY/SECRET jamais testés sur CLOB réel | À valider avant live |
| WALLET_PRIVATE_KEY vs METAMASK_PRIVATE_KEY | À clarifier avant live |
| Gamma API 404 → CONVERGENCE_STRAT bloquée | À investiguer |
| Après kill switch → vérifier `strategy_registry.json` ET `strategy_lifecycle.json` | Reset compte ≠ reset stratégie |
