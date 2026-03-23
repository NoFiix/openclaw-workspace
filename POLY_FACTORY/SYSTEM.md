# POLY_FACTORY/SYSTEM.md — Architecture et fonctionnement

> Dernière mise à jour : Mars 2026
> Voir aussi : `POLY_FACTORY/STATE.md` pour les sources de vérité
> Source : CONTEXT_BUNDLE_POLYMARKET.md + corrections post-audit Mars 2026

---

## OBJECTIF

Générer des profits sur les marchés de prédiction Polymarket via
trading algorithmique multi-stratégies.
Pipeline entièrement automatisé : découverte marché → scoring LLM →
risk management → exécution paper → promotion live.

**Statut actuel :** Paper testing — 9 stratégies actives, 2 positions ouvertes.
50 trades + 14 jours paper requis avant toute promotion live.

---

## STACK TECHNIQUE

| Composant | Technologie |
|-----------|-------------|
| Runtime | Python 3.11 + venv |
| Orchestrateur | PM2 `poly-orchestrator` |
| Bus events | `POLY_FACTORY/core/poly_event_bus.py` — fichiers JSONL |
| État | `POLY_FACTORY/state/` (NE JAMAIS DÉPLACER) |
| LLM | Anthropic Sonnet (analyst, scorer) + Haiku (no_scanner) |
| Exchange | Polymarket CLOB API (paper uniquement pour l'instant) |

---

## STRUCTURE DES DOSSIERS

```
POLY_FACTORY/
├── core/          → bus, data store, audit, account, registry, log_tokens
├── agents/        → feeds, heartbeat, market_analyst, system_monitor
├── strategies/    → arb_scanner, opp_scorer, no_scanner, brownian_sniper...
├── execution/     → paper_engine, live_engine, execution_router
├── risk/          → kill_switch, risk_guardian, global_risk_guard, promotion_gate
├── evaluation/    → evaluator, decay_detector, tuner, scout, backtest
├── connectors/    → connector_polymarket, connector_kalshi, connector_sportsbook
├── schemas/       → JSON schemas bus events
└── state/         → runtime data (NE PAS committer dans git public)
```

---

## PIPELINE COMPLET

```
POLY_MARKET_CONNECTOR
    ↓ feed:price_update (prix YES/NO par market_id)
POLY_DATA_VALIDATOR
    ↓ validation données
POLY_MARKET_ANALYST (Sonnet ~500 tokens/appel, cache par market_id)
    ↓ signal:resolution_parsed (boolean_condition + ambiguity_score)
POLY_OPP_SCORER (Sonnet ~150 tokens/appel, cache 4h par market)
    ↓ trade:signal (proposition de trade)
POLY_RISK_GUARDIAN (7 filtres déterministes)
    ↓ si validé
POLY_EXECUTION_ROUTER (routing paper/live selon registry)
    ↓ execute:paper
POLY_PAPER_ENGINE
    ↓ trade:paper_executed → paper_trades_log.jsonl
POLY_STRATEGY_EVALUATOR (score 8 axes)
    ↓ strategy_scores.json
POLY_STRATEGY_PROMOTION_GATE
    ↓ approbation humaine requise
POLY_CAPITAL_MANAGER
    ↓ live account (uniquement après validation)
```

**Règles absolues du pipeline :**
- Les stratégies dans `strategies/` émettent uniquement `trade:signal` — PAS d'exécution directe
- POLY_EXECUTION_ROUTER route selon le registry (paper/live) — jamais un flag booléen
- POLY_PAPER_ENGINE n'importe jamais `py-clob-client` (paper = simulation)
- Promotion gate DÉCIDE — Capital Manager EXÉCUTE — jamais automatique

---

## 9 STRATÉGIES ACTIVES (PAPER)

| Stratégie | Type | Statut | Trades |
|-----------|------|--------|--------|
| ARB_SCANNER | Dutch Book YES+NO arbitrage | Paper | 0 |
| OPP_SCORER | LLM BUY_YES scoring | Paper | 2 |
| NO_SCANNER | LLM BUY_NO scoring | Paper | 1 (reset 19 mars) |
| BROWNIAN_SNIPER | Mouvement brownien prix | Paper | 0 |
| WEATHER_ARB | Arbitrage météo NOAA | Paper | 0 |
| NEWS_STRAT | News high_impact | Paper | 0 (feed manquant) |
| LATENCY_ARB | Arbitrage latence Binance→Poly | Paper | 0 |
| PAIR_COST | Pair trading coûts | Paper | 0 |
| CONVERGENCE_STRAT | Convergence wallets | Paper | 0 (Gamma API 404) |

**Comptes isolés :** 1 000€ par stratégie, aucun capital partagé.

---

## AGENTS LLM

| Agent | Modèle | Tokens/appel | Cache |
|-------|--------|-------------|-------|
| POLY_MARKET_ANALYST | claude-sonnet-4-6 | ~500 | Par market_id |
| POLY_OPP_SCORER | claude-sonnet-4-6 | ~150 | 4h par market |
| POLY_NO_SCANNER | claude-haiku-4-5-20251001 | ~150 | Permanent |

**Token tracking :** `state/llm/token_costs.jsonl` (system="polymarket")
Agrégé par GLOBAL_TOKEN_TRACKER avec les coûts Trading.

---

## BUS EVENTS — TOPICS CLÉS

| Topic | Type | Producteur | Consommateur |
|-------|------|------------|--------------|
| `feed:price_update` | overwrite | POLY_MARKET_CONNECTOR | POLY_MARKET_ANALYST |
| `signal:resolution_parsed` | queue | POLY_MARKET_ANALYST | OPP_SCORER, NO_SCANNER |
| `trade:signal` | queue | Stratégies | POLY_RISK_GUARDIAN |
| `execute:paper` | queue | POLY_EXECUTION_ROUTER | POLY_PAPER_ENGINE |
| `trade:paper_executed` | queue | POLY_PAPER_ENGINE | POLY_STRATEGY_EVALUATOR |
| `risk:kill_switch` | priority | POLY_RISK_GUARDIAN | Tous |
| `system:agent_disabled` | priority | Orchestrateur | POLY_SYSTEM_MONITOR |
| `news:high_impact` | queue | ⚠️ MANQUANT | NEWS_STRAT |

**⚠️ `news:high_impact` n'a pas de producteur** — bridge JS→Python non implémenté.
NEWS_STRAT est donc inopérante tant que ce feed n'est pas déployé.

---

## RÈGLES BUS POLY — CRITIQUE

Le bus `poly_event_bus.py` utilise un modèle pub/sub multi-consumer.

**Règle fondamentale (DEC-013) :**
- `_acked_ids` est dans `compact()` UNIQUEMENT
- `poll()` filtre uniquement via `_consumer_processed[consumer_id]`
- Ne jamais remettre `_acked_ids` dans `poll()` — casse le multi-consumer

**Rétention :** `compact(max_age_hours=1)` — fenêtre 1h (4x marge consumer le plus lent)

---

## RISK MANAGEMENT

### Kill switch par stratégie
- Seuil : -5% daily, -30% total par stratégie
- Fichier : `state/risk/kill_switch_status.json`

### Kill switch global
- Seuil : pertes cumulées ≥ 4 000€ → ARRET_TOTAL
- Fichier : `state/risk/global_risk_state.json`
- Statuts : NORMAL / ALERTE / CRITIQUE / ARRET_TOTAL

### Promotion gate
- Conditions minimum : 50 trades paper + 14 jours paper
- Approbation humaine obligatoire avant tout passage live
- Jamais automatique

---

## LOGIQUE P&L — RÈGLES MÉTIER CRITIQUES

```
Capital par stratégie = capital.initial (1000€)
Capital engagé        = somme des positions ouvertes
Capital disponible    = capital.initial - capital engagé
P&L réalisé           = uniquement sur marchés RÉSOLUS
P&L non réalisé       = positions ouvertes (unrealized)
```

**Une position ouverte n'est PAS une perte.**
Le gain/perte est définitif uniquement à la résolution du marché.

**Ne jamais utiliser :**
- `capital.current` comme référence (il déduit déjà les positions → double déduction)
- `acc.pnl.total` comme P&L réalisé (représente le coût d'achat des positions ouvertes)

---

## ÉVALUATION DES STRATÉGIES

POLY_STRATEGY_EVALUATOR score chaque stratégie sur 8 axes.
POLY_STRATEGY_PROMOTION_GATE décide la promotion paper → live.

Critères de promotion :
- 50 trades paper minimum
- 14 jours paper minimum
- Score évaluateur suffisant
- Approbation humaine

---

## VARIABLES D'ENVIRONNEMENT

| Variable | Usage |
|----------|-------|
| `ANTHROPIC_API_KEY` | Appels LLM |
| `POLY_API_KEY` / `POLY_SECRET` | Polymarket CLOB API (live uniquement) |
| `POLY_TELEGRAM_BOT_TOKEN` | Alertes Telegram POLY |
| `POLY_TELEGRAM_CHAT_ID` | Canal Telegram POLY |
| `POLY_BASE_PATH` | Override chemin state/ POLY_FACTORY |

**⚠️ Credentials Polymarket (POLY_API_KEY, POLY_SECRET) :** validité
sur le CLOB API réel jamais testée. À valider avant tout passage live.

---

## COMMANDES UTILES

```bash
# État du poly-orchestrator
pm2 show poly-orchestrator | grep -E "status|cpu|memory|restart"

# Logs récents
pm2 logs poly-orchestrator --lines 50

# Positions ouvertes
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/portfolio_state.json \
  | python3 -m json.tool

# Capital et P&L par stratégie
for f in ~/openclaw/workspace/POLY_FACTORY/state/accounts/ACC_POLY_*.json; do
  echo "=== $(basename $f) ==="
  cat "$f" | python3 -m json.tool \
    | grep -E "capital|pnl|trades|status"
done

# État risque global
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/global_risk_state.json \
  | python3 -m json.tool

# Kill switch par stratégie
cat ~/openclaw/workspace/POLY_FACTORY/state/risk/kill_switch_status.json \
  | python3 -m json.tool

# Coûts LLM POLY
tail -5 ~/openclaw/workspace/POLY_FACTORY/state/llm/token_costs.jsonl \
  | python3 -m json.tool

# Scores stratégies
cat ~/openclaw/workspace/POLY_FACTORY/state/evaluation/strategy_scores.json \
  | python3 -m json.tool
```

---

## POINTS D'ATTENTION (AUDIT 2026-03-15)

| Point | Observation | Statut |
|-------|-------------|--------|
| `news:high_impact` sans producteur | Bridge JS→Python non implémenté → NEWS_STRAT inopérante | En backlog |
| WALLET_PRIVATE_KEY vs METAMASK_PRIVATE_KEY | Confusion possible entre les deux clés | À clarifier avant live |
| Credentials Polymarket jamais testées | POLY_API_KEY/SECRET validité inconnue sur CLOB API réel | À tester avant live |
| Gamma API 404 | CONVERGENCE_STRAT bloquée | À investiguer |

---

## PIÈGES CONNUS

- **Bus _acked_ids class-level** : ne JAMAIS remettre dans `poll()` — casse le multi-consumer et bloque toutes les stratégies (BUG-007, 48h sans trade)
- **NO_SCANNER EDGE_THRESHOLD** : seuil minimum 0.08 — LLM surestime prob_no de ~5% (BUG-008, 364 trades, -4181€)
- **capital.current vs capital.initial** : ne jamais utiliser `current` comme référence → double déduction (BUG-010)
- **pnl.total ≠ P&L réalisé** : `pnl.total` = coût d'achat positions ouvertes (BUG-011)
- **NO_SCANNER stopped après kill switch** : vérifier `strategy_registry.json` ET `strategy_lifecycle.json` après tout incident (BUG-012)
- **MAX_RESTARTS trop agressif** : si agents disabled, vérifier ce paramètre avant de chercher une cause plus complexe
