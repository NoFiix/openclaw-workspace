# summary.md — POLY_FACTORY (Python)

**Date** : 2026-03-15
**Scope** : Système automatisé de trading sur marchés prédictifs (Polymarket)

---

## Mission du système

Portefeuille de stratégies indépendantes sur marchés de prédiction. Chaque stratégie est une unité autonome avec son propre capital (1 000€), ses propres métriques et son propre cycle de vie. Le système découvre de nouvelles stratégies, les teste en paper, les évalue, et ne déploie en live que sur validation humaine explicite. Objectif : identifier les stratégies réellement monétisables et construire un portefeuille diversifié.

---

## Entrée / Sortie principales

| Direction | Description | Tag |
|-----------|-------------|-----|
| **Entrée** | Polymarket Gamma API (marchés, prix YES/NO, volumes) | [OBSERVÉ] |
| **Entrée** | Binance REST API (BTC/ETH prix + orderbook) | [OBSERVÉ] |
| **Entrée** | NWS/NOAA API (prévisions météo 6 stations US) | [OBSERVÉ] |
| **Entrée** | Polymarket wallet positions (Gamma API) | [OBSERVÉ] |
| **Sortie** | Paper trades log (`state/trading/paper_trades_log.jsonl`) | [OBSERVÉ] |
| **Sortie** | Notifications Telegram (via POLY_TRADING_PUBLISHER côté JS) | [OBSERVÉ] |

---

## Mode actuel

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Mode | **PAPER TESTING** (flag `--mode paper` dans `run_orchestrator.py`) | [OBSERVÉ] |
| Démarrage | 2026-03-14T02:51Z | [OBSERVÉ] |
| Durée en paper | ~1.5 jours | [DÉDUIT] |
| Trades exécutés | **0** (aucun paper trade) | [OBSERVÉ] |
| Capital total théorique | 9 × 1 000€ = 9 000€ (fictif) | [OBSERVÉ] |

---

## Statut des 9 stratégies

| # | Stratégie | Capital | PnL | Trades | Drawdown | Status | Tag |
|---|-----------|---------|-----|--------|----------|--------|-----|
| 1 | POLY_ARB_SCANNER | 1 000€ | 0€ | 0 | 0% | paper_testing | [OBSERVÉ] |
| 2 | POLY_WEATHER_ARB | 1 000€ | 0€ | 0 | 0% | paper_testing | [OBSERVÉ] |
| 3 | POLY_LATENCY_ARB | 1 000€ | 0€ | 0 | 0% | paper_testing | [OBSERVÉ] |
| 4 | POLY_BROWNIAN_SNIPER | 1 000€ | 0€ | 0 | 0% | paper_testing | [OBSERVÉ] |
| 5 | POLY_PAIR_COST | 1 000€ | 0€ | 0 | 0% | paper_testing | [OBSERVÉ] |
| 6 | POLY_OPP_SCORER | 1 000€ | 0€ | 0 | 0% | paper_testing | [OBSERVÉ] |
| 7 | POLY_NO_SCANNER | 1 000€ | 0€ | 0 | 0% | paper_testing | [OBSERVÉ] |
| 8 | POLY_CONVERGENCE_STRAT | 1 000€ | 0€ | 0 | 0% | paper_testing | [OBSERVÉ] |
| 9 | POLY_NEWS_STRAT | 1 000€ | 0€ | 0 | 0% | paper_testing | [OBSERVÉ] |

**Cohérence capital** : Capital total théorique = 9 000€. Capital réel total dans les comptes = 9 000€. Aucun écart. [OBSERVÉ]

**Classement par performance** : N/A — 0 trades exécutés, aucune métrique de performance disponible. [OBSERVÉ]

---

## Kill switch global

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Statut global risk | **NORMAL** | [OBSERVÉ] |
| Perte cumulée totale | 0€ | [OBSERVÉ] |
| Seuil ALERTE | 2 000€ (50%) | [OBSERVÉ] |
| Seuil CRITIQUE | 3 000€ (75%) | [OBSERVÉ] |
| Seuil ARRÊT TOTAL | 4 000€ (100%) | [OBSERVÉ] |
| Kill switch par stratégie | Aucun déclenché (0 trades → 0 drawdown) | [OBSERVÉ] |
| Dernière vérification | 2026-03-15T20:38Z | [OBSERVÉ] |

---

## Agents — état de santé

| Catégorie | Actifs | Désactivés | Total | Tag |
|-----------|--------|-----------|-------|-----|
| Agents actifs | 8 | — | 8 | [OBSERVÉ] |
| Agents **disabled** (3+ restarts) | — | **11** | 11 | [OBSERVÉ] |
| **Total** | **8** | **11** | **19** | [OBSERVÉ] |

**Agents désactivés** (ont atteint MAX_RESTARTS=3) :

| Agent | Dernière activité | Raison probable | Tag |
|-------|-------------------|-----------------|-----|
| binance_feed | 2026-03-15T20:36Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |
| wallet_feed | 2026-03-15T20:31Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |
| msa (market_structure_analyzer) | 2026-03-15T20:36Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |
| binance_sig | 2026-03-15T20:36Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |
| wallet_track | 2026-03-15T20:37Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |
| data_val | 2026-03-15T20:37Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |
| arb_scanner | 2026-03-15T20:37Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |
| latency_arb | 2026-03-15T20:37Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |
| brownian | 2026-03-15T20:37Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |
| pair_cost | 2026-03-15T20:37Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |
| exec_router | 2026-03-15T20:36Z | Erreurs récurrentes → 3 restarts | [OBSERVÉ] |

**Anomalie critique** : 11 agents sur 19 sont **disabled**. Parmi eux : `exec_router` (exécution impossible), `binance_feed` (données prix perdues), `arb_scanner` / `latency_arb` / `brownian` / `pair_cost` (4 stratégies mortes). Le pipeline est **majoritairement inopérant**. [OBSERVÉ]

---

## APIs externes — criticité

| API | Usage | Criticité | Si indisponible | Tag |
|-----|-------|-----------|-----------------|-----|
| Polymarket Gamma API | Marchés, prix YES/NO, volumes, positions | **BLOQUANT** | Aucun market data → aucun signal | [OBSERVÉ] |
| Binance REST API | Prix BTC/ETH pour latency_arb, brownian_sniper | SUPPORT | 2 stratégies sans données (les 7 autres continuent) | [OBSERVÉ] |
| NWS/NOAA API | Prévisions météo pour weather_arb | SUPPORT | 1 stratégie sans données | [OBSERVÉ] |
| Polygon RPC | Positions wallet on-chain (stub non implémenté) | INACTIF | wallet_feed retombe sur Gamma API uniquement | [OBSERVÉ] |
| Anthropic API | Sonnet (market_analyst, opp_scorer), Haiku (no_scanner) | SUPPORT | 3 stratégies LLM sans signaux (6 restent) | [OBSERVÉ] |
| Polymarket CLOB API | Exécution ordres live (py-clob-client) | **FUTUR** | Pas d'impact actuel (paper mode) | [OBSERVÉ] |

---

## Coût LLM estimé

| Agent | Modèle | Appels estimés/jour | Coût estimé/jour | Tag |
|-------|--------|---------------------|-------------------|-----|
| POLY_MARKET_ANALYST | Claude Sonnet | ~20 (1× par marché, cache permanent) | ~$0.10 | [DÉDUIT] |
| POLY_OPP_SCORER | Claude Sonnet | ~120 (20 marchés × cache 4h) | ~$0.18 | [DÉDUIT] |
| POLY_NO_SCANNER | Claude Haiku | ~20 (1× par marché, cache permanent) | ~$0.003 | [DÉDUIT] |
| **Total estimé** | — | ~160 appels/jour | **~$0.28/jour (~$8.50/mois)** | [DÉDUIT] |

**Observation** : Le fichier `state/llm/token_costs.jsonl` est **vide** (0 octets). Le token tracking est configuré mais aucun appel LLM n'a été loggé. Ceci confirme que les agents LLM n'ont probablement pas encore fait d'appels (opp_scorer et no_scanner actifs mais 0 trades). [OBSERVÉ]

---

## Top 5 points de fragilité

| # | Fragilité | Sévérité | Tag |
|---|-----------|----------|-----|
| **1** | **11 agents sur 19 disabled** (exec_router, binance_feed, 4 stratégies, etc.) — le pipeline est majoritairement cassé après 1.5 jours | **CRITIQUE** | [OBSERVÉ] |
| **2** | **poly-orchestrator à 98% CPU** (C-01) — boucle 2s avec I/O thrashing sur pending_events.jsonl (70k events) | **ÉLEVÉ** | [OBSERVÉ] |
| **3** | **Bus pending_events.jsonl = 70k events** (19 Mo) vs 22k processed — backlog croissant sans compaction suffisante | **ÉLEVÉ** | [OBSERVÉ] |
| **4** | **WALLET_PRIVATE_KEY absent** (U-02) — `place_order()` crashera en mode live | **ÉLEVÉ** (bloquant pour live) | [OBSERVÉ] |
| **5** | **0 trades en 1.5 jours** — aucune stratégie n'a produit un signal validé, cause à diagnostiquer | **MOYEN** | [OBSERVÉ] |
