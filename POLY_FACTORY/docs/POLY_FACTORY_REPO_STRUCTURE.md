# POLY_FACTORY — Structure du Repo

> **Version 1.0 — 12 mars 2026**
> Structure officielle du repo POLY_FACTORY pour Claude Code.
> Chaque fichier a un emplacement défini. Aucun fichier ne doit être créé en dehors de cette structure.

---

## Arborescence Complète

```
POLY_FACTORY/
│
├── CLAUDE.md                                    ← Règles pour Claude Code (relu à chaque session)
├── .env                                         ← Secrets (JAMAIS commité dans Git)
├── .gitignore                                   ← Exclut .env, state/, __pycache__/
│
├── docs/                                        ← Documents de référence (lecture seule)
│   ├── POLY_FACTORY_ARCHITECTURE.md
│   ├── POLY_FACTORY_PIPELINE.md
│   ├── POLY_FACTORY_IMPLEMENTATION_PLAN.md
│   ├── POLY_FACTORY_DEV_BACKLOG.md
│   └── POLY_FACTORY_REPO_STRUCTURE.md           ← Ce fichier
│
├── core/                                        ← Infrastructure système
│   ├── poly_event_bus.py                        ← Bus de communication (JSON Lines + polling)
│   ├── poly_data_store.py                       ← Couche de persistance centralisée
│   ├── poly_audit_log.py                        ← Journalisation immuable append-only
│   ├── poly_strategy_account.py                 ← Modèle de données capital (1 000€ par stratégie)
│   ├── poly_strategy_registry.py                ← Registre vie logique des stratégies
│   └── poly_factory_orchestrator.py             ← Chef d'orchestre (state machine, cycles, routing)
│
├── agents/                                      ← Data feeds + signal agents + monitoring
│   ├── poly_market_connector.py                 ← Abstraction multi-plateformes (interface ABC)
│   ├── poly_binance_feed.py                     ← WebSocket Binance prix BTC/ETH + orderbook
│   ├── poly_noaa_feed.py                        ← REST NWS prévisions météo 6 villes US
│   ├── poly_wallet_feed.py                      ← REST Polymarket + Polygon RPC positions wallets
│   ├── poly_data_validator.py                   ← Filtre données corrompues (Filtre 0)
│   ├── poly_binance_signals.py                  ← OBI, CVD, VWAP, Momentum → score [-1,+1]
│   ├── poly_market_structure_analyzer.py        ← Liquidité, spread, slippage → score 0-100
│   ├── poly_wallet_tracker.py                   ← EV scoring, spécialisation, convergence wallets
│   ├── poly_market_analyst.py                   ← Parse critères résolution via Sonnet (cache)
│   ├── poly_system_monitor.py                   ← Surveillance agents, APIs, VPS, cohérence
│   └── poly_heartbeat.py                        ← Détection agents stale + restart auto
│
├── strategies/                                  ← Stratégies UNIQUEMENT (émettent des signaux)
│   ├── poly_arb_scanner.py                      ← Bundle arb YES+NO + Dutch Book
│   ├── poly_weather_arb.py                      ← Arb NOAA vs buckets Polymarket
│   ├── poly_latency_arb.py                      ← Lag Binance→Polymarket marchés 5-min
│   ├── poly_brownian_sniper.py                  ← Brownian Motion dernières 60s
│   ├── poly_pair_cost.py                        ← Accumulation asymétrique marchés 15-min
│   ├── poly_opp_scorer.py                       ← Marchés haute probabilité ≥ 85%
│   ├── poly_no_scanner.py                       ← Marchés NO > 95¢
│   ├── poly_convergence_strat.py                ← 3+ wallets convergent
│   └── poly_news_strat.py                       ← Event-driven via NEWS_SCORING
│
├── execution/                                   ← Moteurs d'exécution (paper et live SÉPARÉS)
│   ├── poly_paper_execution_engine.py           ← Simulation PURE (AUCUN import py-clob-client)
│   ├── poly_live_execution_engine.py            ← Exécution réelle on-chain (py-clob-client)
│   ├── poly_execution_router.py                 ← Route paper/live selon Registry (< 50 lignes)
│   └── poly_order_splitter.py                   ← Découpe ordres en tranches calibrées
│
├── risk/                                        ← Gestion du risque + promotion
│   ├── poly_kill_switch.py                      ← Override par stratégie/session (5 niveaux)
│   ├── poly_risk_guardian.py                    ← Protection portefeuille (exposure, positions)
│   ├── poly_global_risk_guard.py                ← Plafond perte 4 000€ (4 niveaux, arrêt total)
│   ├── poly_capital_manager.py                  ← Gestion accounts, crée comptes live après Gate
│   ├── poly_kelly_sizer.py                      ← Taille position Half/Quarter Kelly par compte
│   └── poly_strategy_promotion_gate.py          ← 10 checks paper→live (DÉCIDE, ne crée rien)
│
├── evaluation/                                  ← Évaluation + recherche + optimisation
│   ├── poly_strategy_evaluator.py               ← Score 8 axes, verdicts, classement normalisé
│   ├── poly_decay_detector.py                   ← Rolling 7j vs 30j, sévérités HEALTHY→CRITICAL
│   ├── poly_performance_logger.py               ← Agrégation métriques, milestones
│   ├── poly_compounder.py                       ← Leçons nightly via Compound Learning
│   ├── poly_strategy_tuner.py                   ← Recommandations paramètres post-50 trades
│   ├── poly_strategy_scout.py                   ← Veille hebdomadaire nouvelles stratégies
│   └── poly_backtest_engine.py                  ← Replay historique (outil de tri, PAS validation)
│
├── connectors/                                  ← Connecteurs plateformes de marchés de prédiction
│   ├── connector_polymarket.py                  ← py-clob-client + WebSocket CLOB + Gamma API
│   ├── connector_kalshi.py                      ← Kalshi REST API (futur Phase 2)
│   ├── connector_sportsbook.py                  ← À définir (futur Phase 3)
│   └── POLY_MARKET_CONNECTOR.config.json        ← Liste des connecteurs actifs
│
├── schemas/                                     ← Schémas JSON pour bus events et modèles
│   ├── event_envelope.json                      ← Format commun de tout événement bus
│   ├── feed_price_update.json                   ← Payload feed:price_update
│   ├── feed_binance_update.json                 ← Payload feed:binance_update
│   ├── feed_noaa_update.json                    ← Payload feed:noaa_update
│   ├── feed_wallet_update.json                  ← Payload feed:wallet_update
│   ├── signal_binance_score.json                ← Payload signal:binance_score
│   ├── signal_wallet_convergence.json           ← Payload signal:wallet_convergence
│   ├── signal_resolution_parsed.json            ← Payload signal:resolution_parsed
│   ├── trade_signal.json                        ← Payload trade:signal
│   ├── trade_validated.json                     ← Payload trade:validated
│   ├── trade_executed.json                      ← Payload trade:paper_executed / trade:live_executed
│   ├── risk_kill_switch.json                    ← Payload risk:kill_switch
│   ├── risk_global_status.json                  ← Payload risk:global_status
│   ├── promotion_request.json                   ← Payload promotion:request
│   ├── promotion_approved.json                  ← Payload promotion:approved
│   ├── promotion_denied.json                    ← Payload promotion:denied
│   ├── eval_score_updated.json                  ← Payload eval:score_updated
│   ├── data_validation_failed.json              ← Payload data:validation_failed
│   ├── strategy_account.json                    ← Schéma POLY_STRATEGY_ACCOUNT
│   └── strategy_registry_entry.json             ← Schéma entrée POLY_STRATEGY_REGISTRY
│
├── tests/                                       ← Un fichier test par composant
│   ├── test_event_bus.py
│   ├── test_data_store.py
│   ├── test_audit_log.py
│   ├── test_strategy_account.py
│   ├── test_strategy_registry.py
│   ├── test_market_connector.py
│   ├── test_binance_feed.py
│   ├── test_noaa_feed.py
│   ├── test_wallet_feed.py
│   ├── test_data_validator.py
│   ├── test_binance_signals.py
│   ├── test_market_structure.py
│   ├── test_wallet_tracker.py
│   ├── test_market_analyst.py
│   ├── test_arb_scanner.py
│   ├── test_weather_arb.py
│   ├── test_latency_arb.py
│   ├── test_brownian_sniper.py
│   ├── test_pair_cost.py
│   ├── test_opp_scorer.py
│   ├── test_no_scanner.py
│   ├── test_convergence_strat.py
│   ├── test_news_strat.py
│   ├── test_paper_execution.py
│   ├── test_live_execution.py
│   ├── test_execution_router.py
│   ├── test_order_splitter.py
│   ├── test_kill_switch.py
│   ├── test_risk_guardian.py
│   ├── test_global_risk_guard.py
│   ├── test_capital_manager.py
│   ├── test_kelly_sizer.py
│   ├── test_promotion_gate.py
│   ├── test_strategy_evaluator.py
│   ├── test_decay_detector.py
│   ├── test_performance_logger.py
│   ├── test_backtest_engine.py
│   ├── test_orchestrator.py
│   ├── test_system_monitor.py
│   ├── test_bus_idempotence.py                  ← Test d'intégration bus
│   ├── test_paper_e2e.py                        ← Test end-to-end paper trading
│   ├── test_guards.py                           ← Test d'intégration garde-fous
│   ├── test_api_failures.py                     ← Test échecs API + reconnexion
│   └── test_restart.py                          ← Test reprise après crash
│
├── references/                                  ← Fichiers de configuration statique
│   ├── station_mapping.json                     ← 6 stations NOAA (KLGA, KORD, KMIA, KDAL, KSEA, KATL)
│   ├── tracked_wallets.json                     ← Liste initiale des wallets à suivre
│   ├── validation_rules.json                    ← Seuils configurables du POLY_DATA_VALIDATOR
│   ├── evaluator_weights.json                   ← Poids des 8 axes du POLY_STRATEGY_EVALUATOR
│   ├── weather_market_mapping.json              ← Mapping villes → marchés Polymarket
│   ├── nightly_schedule.json                    ← Horaires du cycle nightly (03:00-04:00 UTC)
│   ├── filter_chain_order.json                  ← Ordre des 7 filtres de la chaîne de tradabilité
│   └── monitoring_thresholds.json               ← Seuils du POLY_SYSTEM_MONITOR
│
├── state/                                       ← Données runtime (VPS only, JAMAIS dans Git)
│   ├── accounts/                                ← POLY_STRATEGY_ACCOUNT (un JSON par stratégie)
│   │   ├── ACC_POLY_ARB_SCANNER.json
│   │   └── archive/                             ← Accounts des stratégies stoppées
│   ├── feeds/                                   ← Données temps réel (écrasées en continu)
│   │   ├── polymarket_prices.json
│   │   ├── binance_raw.json
│   │   ├── binance_signals.json
│   │   ├── noaa_forecasts.json
│   │   ├── wallet_raw_positions.json
│   │   ├── wallet_signals.json
│   │   └── market_structure.json
│   ├── trading/
│   │   ├── paper_trades_log.jsonl               ← JSON Lines append-only
│   │   ├── live_trades_log.jsonl                ← JSON Lines append-only
│   │   └── positions_by_strategy/
│   ├── evaluation/
│   │   ├── strategy_scores.json
│   │   ├── strategy_rankings.json
│   │   ├── tradability_reports.json
│   │   ├── decay_alerts.json
│   │   └── tuning_recommendations.json
│   ├── risk/
│   │   ├── kill_switch_status.json
│   │   └── global_risk_state.json
│   ├── research/
│   │   ├── scouted_strategies.json
│   │   ├── backtest_results/
│   │   └── resolutions_cache.json
│   ├── orchestrator/
│   │   ├── system_state.json
│   │   ├── strategy_lifecycle.json
│   │   └── cycle_log.json
│   ├── bus/
│   │   ├── pending_events.jsonl                 ← Bus principal (append-only)
│   │   ├── processed_events.jsonl
│   │   └── dead_letter.jsonl
│   ├── audit/
│   │   ├── audit_YYYY_MM_DD.jsonl               ← Un fichier par jour (immuable)
│   │   └── archive/
│   ├── registry/
│   │   └── strategy_registry.json
│   └── human/
│       ├── approvals.json
│       └── decisions_log.jsonl
│
└── tasks/                                       ← Suivi développement
    ├── todo.md                                  ← Sprint courant (référence POLY-XXX)
    └── lessons.md                               ← Erreurs capturées + règles de prévention
```

---

## Règles de Placement

| Je crée... | Le fichier va dans |
|---|---|
| Un composant fondamental (bus, store, audit, orchestrator, account, registry) | `core/` |
| Un feed de données ou un agent de signal | `agents/` |
| Une stratégie de trading | `strategies/` |
| Un moteur d'exécution (paper ou live) ou le router | `execution/` |
| Un composant de risque ou de promotion | `risk/` |
| Un composant d'évaluation, de recherche ou d'optimisation | `evaluation/` |
| Un connecteur de plateforme (Polymarket, Kalshi...) | `connectors/` |
| Un schéma JSON pour un event bus ou un modèle | `schemas/` |
| Un test | `tests/` |
| Un fichier de configuration statique | `references/` |
| Des données runtime | `state/{category}/` |
| Un document de référence | `docs/` |

**En cas de doute** : si un fichier ne rentre dans aucune catégorie, il ne devrait probablement pas exister. Discuter avant de créer.

---

## Ce qui va dans Git vs ce qui reste sur le VPS

| Git (commité) | VPS only (pas dans Git) |
|---|---|
| `CLAUDE.md` | `state/` (toutes les données runtime) |
| `docs/` | `.env` (secrets) |
| `core/`, `agents/`, `strategies/`, `execution/`, `risk/`, `evaluation/` | `__pycache__/` |
| `connectors/`, `schemas/`, `tests/`, `references/`, `tasks/` | |

Le `.gitignore` doit contenir :

```
.env
state/
__pycache__/
*.pyc
```

---

## Schémas : Ce qu'ils Contiennent

Chaque fichier dans `schemas/` est un JSON Schema qui définit les champs obligatoires, les types et les valeurs valides d'un payload bus ou d'un modèle de données. Exemples :

**`schemas/trade_signal.json`** définit que chaque `trade:signal` doit contenir : `strategy` (string), `account_id` (string), `market_id` (string), `platform` (string), `direction` (string), `confidence` (float 0-1), `suggested_size_eur` (float > 0), `signal_type` (string), `signal_detail` (object).

**`schemas/strategy_account.json`** définit la structure d'un `POLY_STRATEGY_ACCOUNT` : `account_id`, `strategy`, `status` (enum), `platform`, `capital` (object), `pnl` (object), `drawdown` (object), `performance` (object), `limits` (object), `status_history` (array).

Les payloads exacts sont documentés dans `docs/POLY_FACTORY_IMPLEMENTATION_PLAN.md` section 7. Les schémas dans `schemas/` sont la version machine-lisible de ces contrats.

---

## Comptage des Fichiers

| Dossier | Fichiers | Rôle |
|---|---|---|
| `core/` | 6 | Infrastructure système |
| `agents/` | 11 | Data + signal + monitoring |
| `strategies/` | 9 | Stratégies de trading |
| `execution/` | 4 | Paper + live + router + splitter |
| `risk/` | 6 | Kill switch, guardian, global risk, capital manager, kelly, promotion gate |
| `evaluation/` | 7 | Evaluator, decay, logger, compounder, tuner, scout, backtest |
| `connectors/` | 3+1 | Polymarket + futurs + config |
| `schemas/` | 20 | Schémas bus events + modèles |
| `tests/` | 42 | Tests unitaires + intégration |
| `references/` | 8 | Configs statiques |
| `state/` | ~30 | Données runtime (VPS) |
| `docs/` | 5 | Documents de référence |
| `tasks/` | 2 | Suivi développement |

**Total code source** : 46 fichiers Python.
**Total tests** : 42 fichiers de test.
**Total schémas** : 20 fichiers JSON.

---

*Structure basée sur POLY_FACTORY_ARCHITECTURE v4.0, PIPELINE v4.0, IMPLEMENTATION_PLAN v3.0, DEV_BACKLOG v2.0.*
