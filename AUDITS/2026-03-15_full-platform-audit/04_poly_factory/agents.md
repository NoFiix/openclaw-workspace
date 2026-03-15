# agents.md — Inventaire des composants POLY_FACTORY

**Date** : 2026-03-15
**Scope** : 35+ composants Python dans POLY_FACTORY/

---

## CORE (6 composants)

### 1. poly_event_bus (PolyEventBus)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Bus événementiel file-based (JSONL) avec polling, idempotence, retry, modes (overwrite/queue/cache/priority) | [OBSERVÉ] |
| Criticité | **CORE** — sans lui, aucune communication inter-agents | [DÉDUIT] |
| State files | `bus/pending_events.jsonl` (19 Mo, 70k events), `bus/processed_events.jsonl` (2.5 Mo, 22k events), `bus/dead_letter.jsonl` | [OBSERVÉ] |
| Retry | MAX_RETRIES=3, dead-letter après 3 échecs | [OBSERVÉ] |
| Idempotence | `_acked_ids` (deque maxlen=10 000), persisted dans `processed_events.jsonl` | [OBSERVÉ] |
| Compaction | Automatique toutes les 100 itérations de poll() si >10 000 events | [OBSERVÉ] |

### 2. poly_data_store (PolyDataStore)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Couche de persistance centralisée (JSON/JSONL/SQLite) avec écritures atomiques (tmp→rename) | [OBSERVÉ] |
| Criticité | **CORE** — tous les agents dépendent de lui pour lire/écrire l'état | [DÉDUIT] |
| Sous-dossiers | accounts/, risk/, feeds/, trading/, evaluation/, research/, human/, bus/, audit/, orchestrator/, registry/, llm/, memory/, strategies/ | [OBSERVÉ] |

### 3. poly_audit_log (PolyAuditLog)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Log d'audit immutable, append-only, rotation quotidienne | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| State files | `audit/audit_{YYYY_MM_DD}.jsonl` (427 events aujourd'hui) | [OBSERVÉ] |
| Rétention | 90 jours | [OBSERVÉ] |

### 4. poly_strategy_account (PolyStrategyAccount)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Compte capital isolé par stratégie (1 000€), P&L, drawdown, high/low water mark | [OBSERVÉ] |
| Criticité | **CORE** — gère le capital de chaque stratégie | [DÉDUIT] |
| Bus publié | `account:created`, `account:trade_recorded`, `account:status_updated` | [OBSERVÉ] |
| State files | `accounts/ACC_POLY_{STRATEGY}.json` (9 fichiers) | [OBSERVÉ] |
| Thread-safety | `threading.Lock()` | [OBSERVÉ] |

### 5. poly_strategy_registry (PolyStrategyRegistry)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Registre central du cycle de vie des stratégies (status, version, paramètres, dates) | [OBSERVÉ] |
| Criticité | **CORE** — détermine le routage paper/live | [DÉDUIT] |
| Bus publié | `registry:strategy_registered`, `registry:status_updated`, `registry:parameters_updated` | [OBSERVÉ] |
| State files | `registry/strategy_registry.json` | [OBSERVÉ] |

### 6. poly_factory_orchestrator (PolyFactoryOrchestrator)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Routeur de signaux + chaîne de 7 filtres + gestionnaire lifecycle + nightly cycle | [OBSERVÉ] |
| Criticité | **CORE** — cerveau du système | [DÉDUIT] |
| Bus consommé | `trade:signal`, `risk:kill_switch`, `risk:global_status`, `eval:score_updated`, `promotion:approved`, `signal:resolution_parsed`, `feed:price_update` | [OBSERVÉ] |
| Bus publié | `trade:validated`, `promotion:request` | [OBSERVÉ] |
| 7 filtres | data_quality → microstructure → resolution → sizing → kill_switch → risk_guardian → capital_manager | [OBSERVÉ] |
| State files | `orchestrator/system_state.json`, `orchestrator/strategy_lifecycle.json`, `orchestrator/cycle_log.json` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Nightly | Évaluation, compaction bus, rotation audit | [OBSERVÉ] |

---

## DATA FEEDS (5 agents)

### 7. poly_binance_feed (PolyBinanceFeed)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Fetch prix BTC/ETH + orderbook depuis Binance REST API | [OBSERVÉ] |
| Criticité | SUPPORT — alimente latency_arb et brownian_sniper | [DÉDUIT] |
| Bus publié | `feed:binance_update` | [OBSERVÉ] |
| State files | `feeds/binance_raw.json` | [OBSERVÉ] |
| Schedule | 30s | [OBSERVÉ] |
| Timeout | HTTP 30s, reconnect backoff exponentiel (1s → 30s) | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts atteints) | [OBSERVÉ] |

### 8. poly_noaa_feed (PolyNoaaFeed)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Fetch prévisions météo NWS/NOAA pour 6 stations US (LGA, ORD, MIA, DAL, SEA, ATL) | [OBSERVÉ] |
| Criticité | SUPPORT — alimente weather_arb | [DÉDUIT] |
| Bus publié | `feed:noaa_update` | [OBSERVÉ] |
| State files | `feeds/noaa_forecasts.json` | [OBSERVÉ] |
| Schedule | 120s | [OBSERVÉ] |
| Timeout | HTTP 30s | [OBSERVÉ] |
| Statut | **ACTIF** (2 restarts) | [OBSERVÉ] |

### 9. poly_wallet_feed (PolyWalletFeed)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Fetch positions wallet Polymarket via Gamma API (Polygon RPC = stub) | [OBSERVÉ] |
| Criticité | SUPPORT — alimente wallet_tracker → convergence_strat | [DÉDUIT] |
| Bus publié | `feed:wallet_update` | [OBSERVÉ] |
| State files | `feeds/wallet_raw_positions.json` | [OBSERVÉ] |
| Schedule | 600s | [OBSERVÉ] |
| Timeout | HTTP 30s, 403 → return empty | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts) | [OBSERVÉ] |

### 10. poly_wallet_tracker (PolyWalletTracker)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Enrichit signaux wallet : EV score, spécialisation, blacklist, convergence (≥3 wallets) | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Bus consommé | `feed:wallet_update` | [OBSERVÉ] |
| Bus publié | `signal:wallet_convergence` | [OBSERVÉ] |
| State files | `feeds/wallet_signals.json` | [OBSERVÉ] |
| Schedule | 60s | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts) | [OBSERVÉ] |

### 11. poly_market_connector (PolyMarketConnector)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Classe de base abstraite définissant l'interface unifiée pour tous les connecteurs de plateforme | [OBSERVÉ] |
| Criticité | **CORE** — interface obligatoire pour les connecteurs | [DÉDUIT] |
| Implémentations | connector_polymarket (actif), connector_kalshi (implémenté), connector_sportsbook (implémenté) | [OBSERVÉ] |
| Schedule | 300s (pour connector_polymarket via orchestrateur) | [OBSERVÉ] |
| Statut | **ACTIF** (connector = 0 restarts) | [OBSERVÉ] |

---

## ANALYSE (5 agents)

### 12. poly_data_validator (PolyDataValidator)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Filtre qualité des données : valide tous les payloads feed contre des règles (prix, binance, noaa, wallet) | [OBSERVÉ] |
| Criticité | SUPPORT — gate de qualité avant stratégies | [DÉDUIT] |
| Bus publié | `data:validation_failed` | [OBSERVÉ] |
| State files | Lit les fichiers feeds directement | [OBSERVÉ] |
| Schedule | 10s | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts) | [OBSERVÉ] |

### 13. poly_market_analyst (PolyMarketAnalyst)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Parse conditions de résolution des marchés via Claude Sonnet LLM (cache permanent par market_id) | [OBSERVÉ] |
| Criticité | SUPPORT — alimente opp_scorer, no_scanner, convergence_strat | [DÉDUIT] |
| Bus publié | `signal:resolution_parsed` | [OBSERVÉ] |
| State files | `research/resolutions_cache.json` | [OBSERVÉ] |
| LLM | **Claude Sonnet** — ~500 tokens/appel, cache permanent | [OBSERVÉ] |
| Schedule | À la demande (appelé par orchestrateur) | [OBSERVÉ] |
| Statut | **ACTIF** (via orchestrateur, pas dans heartbeat) | [DÉDUIT] |

### 14. poly_market_structure_analyzer (PolyMarketStructureAnalyzer)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Calcule métriques microstructure : spread, depth, slippage, executability 0-100 | [OBSERVÉ] |
| Criticité | **CORE** — filtre 1 de l'orchestrateur (executability ≥40) | [DÉDUIT] |
| Bus publié | `signal:market_structure`, `market:illiquid` | [OBSERVÉ] |
| State files | `feeds/market_structure.json` | [OBSERVÉ] |
| Schedule | 30s | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts) | [OBSERVÉ] |

### 15. poly_binance_signals (PolyBinanceSignals)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Transforme ticks Binance en 4 signaux composites : OBI, CVD, VWAP position, Momentum | [OBSERVÉ] |
| Criticité | SUPPORT — alimente latency_arb et brownian_sniper | [DÉDUIT] |
| Bus publié | `signal:binance_score` | [OBSERVÉ] |
| State files | `feeds/binance_signals.json` | [OBSERVÉ] |
| Schedule | 10s | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts) | [OBSERVÉ] |

---

## STRATÉGIES (9 agents)

### 16. poly_arb_scanner (PolyArbScanner)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Arbitrage bundle (Dutch Book) : détecte yes_ask + no_ask < 0.97 | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| Bus consommé | `feed:price_update`, `signal:market_structure` | [OBSERVÉ] |
| Bus publié | `trade:signal` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 5s | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts) | [OBSERVÉ] |

### 17. poly_weather_arb (PolyWeatherArb)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Arb météo : NOAA confidence vs YES ask Polymarket (edge > 0.15) | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| Bus consommé | `feed:noaa_update`, `feed:price_update` | [OBSERVÉ] |
| Bus publié | `trade:signal` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 60s | [OBSERVÉ] |
| Statut | **ACTIF** (2 restarts) | [OBSERVÉ] |

### 18. poly_latency_arb (PolyLatencyArb)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Arb de latence Binance→Polymarket : implied_prob - yes_ask > 0.10 | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| Bus consommé | `signal:binance_score`, `feed:price_update` | [OBSERVÉ] |
| Bus publié | `trade:signal` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 5s | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts) | [OBSERVÉ] |

### 19. poly_brownian_sniper (PolyBrownianSniper)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | GBM pricing binaire : estime P(S>K) via volatilité, compare au ask | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| Bus consommé | `signal:binance_score`, `feed:price_update` | [OBSERVÉ] |
| Bus publié | `trade:signal` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 5s | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts) | [OBSERVÉ] |

### 20. poly_pair_cost (PolyPairCost)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Pair-cost directionnel : utilise bid opposé comme fair-value | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| Bus consommé | `feed:price_update`, `signal:market_structure` | [OBSERVÉ] |
| Bus publié | `trade:signal` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 5s | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts) | [OBSERVÉ] |

### 21. poly_opp_scorer (PolyOppScorer)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Scoring YES via Claude Sonnet : estime P(YES) à partir de la condition de résolution (cache 4h) | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| Bus consommé | `signal:resolution_parsed`, `feed:price_update` | [OBSERVÉ] |
| Bus publié | `trade:signal` | [OBSERVÉ] |
| LLM | **Claude Sonnet** — 150 tokens max, cache TTL 4h | [OBSERVÉ] |
| Schedule | 30s | [OBSERVÉ] |
| Statut | **ACTIF** (2 restarts) | [OBSERVÉ] |

### 22. poly_no_scanner (PolyNoScanner)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Scoring NO via Claude Haiku : estime P(YES) 1× par marché (cache permanent) | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| Bus consommé | `signal:resolution_parsed`, `feed:price_update` | [OBSERVÉ] |
| Bus publié | `trade:signal` | [OBSERVÉ] |
| LLM | **Claude Haiku** — 150 tokens max, cache permanent | [OBSERVÉ] |
| Schedule | 30s | [OBSERVÉ] |
| Statut | **ACTIF** (0 restarts) | [OBSERVÉ] |

### 23. poly_convergence_strat (PolyConvergenceStrat)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Convergence wallet : ≥3 wallets same direction + résolution claire | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| Bus consommé | `signal:wallet_convergence`, `signal:resolution_parsed` | [OBSERVÉ] |
| Bus publié | `trade:signal` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 30s | [OBSERVÉ] |
| Statut | **ACTIF** (0 restarts) | [OBSERVÉ] |

### 24. poly_news_strat (PolyNewsStrat)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Réaction news : POSITIVE→BUY_YES, NEGATIVE→BUY_NO si impact ≥0.70 | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| Bus consommé | `news:high_impact`, `feed:price_update` | [OBSERVÉ] |
| Bus publié | `trade:signal` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 30s | [OBSERVÉ] |
| Statut | **ACTIF** (0 restarts) | [OBSERVÉ] |

---

## EXÉCUTION (4 composants)

### 25. poly_execution_router (PolyExecutionRouter)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Route `trade:validated` → `execute:paper` OU `execute:live` selon statut registry | [OBSERVÉ] |
| Criticité | **CORE** — pont entre validation et exécution | [DÉDUIT] |
| Bus consommé | `trade:validated` | [OBSERVÉ] |
| Bus publié | `execute:paper`, `execute:live` | [OBSERVÉ] |
| LLM | Aucun, **pas d'import py-clob-client** | [OBSERVÉ] |
| Schedule | 2s | [OBSERVÉ] |
| Statut | **DISABLED** (3 restarts) | [OBSERVÉ] |

### 26. poly_paper_execution_engine (PolyPaperExecutionEngine)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Simule trades paper : prix réalistes, slippage, fees 0.2%, débit du compte | [OBSERVÉ] |
| Criticité | **CORE** (en paper mode) | [DÉDUIT] |
| Bus consommé | `execute:paper` | [OBSERVÉ] |
| Bus publié | `trade:paper_executed` | [OBSERVÉ] |
| State files | `trading/paper_trades_log.jsonl` (append), lit `feeds/market_structure.json` | [OBSERVÉ] |
| LLM | Aucun, **pas d'import py-clob-client** | [OBSERVÉ] |
| Schedule | 2s | [OBSERVÉ] |
| Statut | **ACTIF** (1 restart) | [OBSERVÉ] |

### 27. poly_live_execution_engine (PolyLiveExecutionEngine)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Exécution on-chain via py-clob-client (lazy load). Retries, timeout 30s. | [OBSERVÉ] |
| Criticité | **CORE** (en live mode, actuellement inactif) | [DÉDUIT] |
| Bus consommé | `execute:live` | [OBSERVÉ] |
| Bus publié | `trade:live_executed` | [OBSERVÉ] |
| State files | `trading/live_trades_log.jsonl` (append) | [OBSERVÉ] |
| Retry | MAX_RETRIES=3, RETRY_DELAY=1s, ORDER_TIMEOUT=30s | [OBSERVÉ] |
| Statut | **DORMANT** (aucune stratégie en live) | [DÉDUIT] |

### 28. poly_order_splitter (PolyOrderSplitter)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Découpe grosses positions en tranches depth-aware pour minimiser slippage | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Statut | **DORMANT** (pas d'ordres à splitter) | [DÉDUIT] |

---

## RISK (6 composants)

### 29. poly_risk_guardian (PolyRiskGuardian)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Garde portefeuille : max 5 positions, max 80% exposure, max 40%/catégorie | [OBSERVÉ] |
| Criticité | **CORE** — filtre 6 de l'orchestrateur | [DÉDUIT] |
| Bus publié | `risk:portfolio_check` | [OBSERVÉ] |
| State files | `risk/portfolio_state.json` | [OBSERVÉ] |
| Limites | MAX_POSITIONS=5, MAX_EXPOSURE=80%, MAX_CATEGORY=40% | [OBSERVÉ] |

### 30. poly_kill_switch (PolyKillSwitch)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Kill switch par stratégie : 5 niveaux (OK→WARNING→PAUSE_DAILY→PAUSE_SESSION→STOP_STRATEGY) | [OBSERVÉ] |
| Criticité | **CORE** — filtre 5 de l'orchestrateur | [DÉDUIT] |
| Bus publié | `risk:kill_switch` | [OBSERVÉ] |
| State files | `risk/kill_switch_status.json` | [OBSERVÉ] |
| Seuils | Daily drawdown -5%, total drawdown -30%, 3 pertes consécutives, feed stale 300s | [OBSERVÉ] |

### 31. poly_global_risk_guard (PolyGlobalRiskGuard)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Garde global : perte cumulée totale toutes stratégies. 4 niveaux (NORMAL→ALERTE→CRITIQUE→ARRÊT_TOTAL) | [OBSERVÉ] |
| Criticité | **CORE** — override tout si seuil atteint | [DÉDUIT] |
| Bus consommé | `trade:paper_executed`, `trade:live_executed` | [OBSERVÉ] |
| Bus publié | `risk:global_halt` | [OBSERVÉ] |
| State files | `risk/global_risk_state.json` | [OBSERVÉ] |
| Seuil | -4 000€ → ARRÊT_TOTAL | [OBSERVÉ] |
| Statut | **NORMAL** (perte 0€) | [OBSERVÉ] |

### 32. poly_kelly_sizer (PolyKellySizer)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Sizing Kelly half-Kelly : f* = (p·b - q) / b, cappé à 3% du capital du compte | [OBSERVÉ] |
| Criticité | **CORE** — filtre 4 de l'orchestrateur | [DÉDUIT] |
| LLM | Aucun | [OBSERVÉ] |

### 33. poly_capital_manager (PolyCapitalManager)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Vérifie capital disponible avant trade (proposed_size ≤ available) | [OBSERVÉ] |
| Criticité | **CORE** — filtre 7 de l'orchestrateur | [DÉDUIT] |
| State files | Lit `accounts/ACC_POLY_*.json` | [OBSERVÉ] |

### 34. poly_strategy_promotion_gate (PolyStrategyPromotionGate)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | 10 checks avant approbation humaine : backtest, paper trades ≥50, jours ≥14, Sharpe, drawdown | [OBSERVÉ] |
| Criticité | **CORE** — gate obligatoire avant live | [DÉDUIT] |
| Bus consommé | `promotion:request` | [OBSERVÉ] |
| Bus publié | `promotion:proposed` | [OBSERVÉ] |
| State files | `research/promotion_checks.json` | [OBSERVÉ] |

---

## ÉVALUATION (7 composants)

### 35. poly_performance_logger (PolyPerformanceLogger)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Log P&L, Sharpe, win rate, drawdown max par stratégie | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Bus consommé | `trade:paper_executed`, `trade:live_executed` | [OBSERVÉ] |
| State files | `evaluation/strategy_scores.json`, `trading/positions_by_strategy/{strategy}.json` | [OBSERVÉ] |

### 36. poly_strategy_evaluator (PolyStrategyEvaluator)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Score paper strategies 0-100 (seuil promotion ≥60, min 50 trades) | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Bus publié | `eval:score_updated` | [OBSERVÉ] |
| State files | `evaluation/strategy_scores.json`, `evaluation/strategy_rankings.json` | [OBSERVÉ] |
| Fréquence | Nightly | [OBSERVÉ] |

### 37. poly_decay_detector (PolyDecayDetector)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Détecte déclin performance (rolling window Sharpe > 20% degradation) | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Bus publié | `eval:decay_alert` | [OBSERVÉ] |
| State files | `evaluation/decay_alerts.json` | [OBSERVÉ] |
| Fréquence | Nightly | [OBSERVÉ] |

### 38. poly_strategy_tuner (PolyStrategyTuner)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Suggestions d'optimisation de paramètres (si win_rate baisse >10%) | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Bus publié | `eval:tuning_recommendation` | [OBSERVÉ] |
| Fréquence | Nightly | [OBSERVÉ] |

### 39. poly_strategy_scout (PolyStrategyScout)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Découverte de nouvelles stratégies, scoring viabilité, détection réactivation | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Bus publié | `research:strategy_scouted`, `eval:reactivation_candidate` | [OBSERVÉ] |
| Fréquence | Hebdomadaire | [OBSERVÉ] |

### 40. poly_compounder (PolyCompounder)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Réinvestit les profits (compounding). Seuil min 100€ profit | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Bus publié | `capital:reallocation` | [OBSERVÉ] |
| Fréquence | Configurable (daily/weekly/monthly) | [OBSERVÉ] |

### 41. poly_backtest_engine (PolyBacktestEngine)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Backtest sur données historiques (pure Python, pas de numpy) | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Bus publié | `backtest:completed` | [OBSERVÉ] |
| Fréquence | À la demande | [OBSERVÉ] |

---

## SYSTÈME (3 composants)

### 42. poly_heartbeat (PolyHeartbeat)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Monitoring liveness : détection agents stale (2× expected_freq), auto-restart, disable après 3 échecs | [OBSERVÉ] |
| Criticité | **CORE** — seul mécanisme de détection de pannes internes | [DÉDUIT] |
| Bus publié | `system:heartbeat`, `system:agent_stale`, `system:agent_disabled` | [OBSERVÉ] |
| State files | `orchestrator/heartbeat_state.json` | [OBSERVÉ] |
| Schedule | 300s | [OBSERVÉ] |
| Seuil stale | 2 × expected_freq_s | [OBSERVÉ] |
| MAX_RESTARTS | 3 | [OBSERVÉ] |

### 43. poly_system_monitor (PolySystemMonitor)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Health check : agents, APIs, infra, cohérence registry/accounts | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Bus publié | `system:health_check`, `system:api_degraded`, `system:infra_warning`, `system:coherence_error` | [OBSERVÉ] |
| Schedule | 300s | [OBSERVÉ] |
| Statut | **ACTIF** — dernier check OK | [OBSERVÉ] |

---

## CONNECTEURS (3)

### 44. connector_polymarket (ConnectorPolymarket)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Connexion Polymarket via Gamma API (public) + py-clob-client (trading live) | [OBSERVÉ] |
| Criticité | **CORE** — seul connecteur actif | [DÉDUIT] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 45. connector_kalshi (ConnectorKalshi)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Connexion Kalshi via REST API, conversion odds American→décimal→probabilité | [OBSERVÉ] |
| Criticité | FUTUR | [DÉDUIT] |
| Statut | **DORMANT** (implémenté, pas connecté) | [DÉDUIT] |

### 46. connector_sportsbook (ConnectorSportsbook)
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Connexion sportsbooks, conversion formats odds multiples | [OBSERVÉ] |
| Criticité | FUTUR | [DÉDUIT] |
| Statut | **DORMANT** (implémenté, pas connecté) | [DÉDUIT] |

---

## Matrice de dépendances

| Composant | Dépend de | Fournit à |
|-----------|-----------|-----------|
| connector_polymarket | Polymarket API | poly_market_structure_analyzer, toutes stratégies |
| poly_binance_feed | Binance API | poly_binance_signals |
| poly_binance_signals | poly_binance_feed | poly_latency_arb, poly_brownian_sniper |
| poly_noaa_feed | NWS/NOAA API | poly_weather_arb |
| poly_wallet_feed | Polymarket Gamma API | poly_wallet_tracker |
| poly_wallet_tracker | poly_wallet_feed | poly_convergence_strat |
| poly_market_analyst | Anthropic Sonnet | poly_opp_scorer, poly_no_scanner, poly_convergence_strat |
| poly_market_structure_analyzer | connector_polymarket | orchestrateur (filtre 1), poly_arb_scanner, poly_pair_cost |
| poly_data_validator | Tous les feeds | orchestrateur (qualité) |
| Toutes les stratégies | Feeds + signals | orchestrateur → `trade:signal` |
| poly_factory_orchestrator | `trade:signal` | poly_execution_router → `trade:validated` |
| poly_execution_router | orchestrateur | poly_paper_execution_engine OU poly_live_execution_engine |
| poly_paper_execution_engine | poly_execution_router | poly_performance_logger, poly_global_risk_guard |
| poly_kill_switch | poly_strategy_account | orchestrateur (filtre 5) |
| poly_global_risk_guard | poly_strategy_account (toutes) | orchestrateur (halt global) |
| poly_strategy_evaluator | poly_performance_logger | poly_strategy_promotion_gate |
| poly_heartbeat | Tous les agents (last_seen) | orchestrateur (restart) |

---

## Matrice stratégies ↔ données

| Stratégie | Sources données | Type | Statut |
|-----------|-----------------|------|--------|
| POLY_ARB_SCANNER | feed:price_update + signal:market_structure | Arbitrage bundle | **DISABLED** |
| POLY_WEATHER_ARB | feed:noaa_update + feed:price_update | Arbitrage météo | **ACTIF** |
| POLY_LATENCY_ARB | signal:binance_score + feed:price_update | Arbitrage latence | **DISABLED** |
| POLY_BROWNIAN_SNIPER | signal:binance_score + feed:price_update | Pricing GBM | **DISABLED** |
| POLY_PAIR_COST | feed:price_update + signal:market_structure | Cost directionnel | **DISABLED** |
| POLY_OPP_SCORER | signal:resolution_parsed + feed:price_update | LLM scoring YES | **ACTIF** |
| POLY_NO_SCANNER | signal:resolution_parsed + feed:price_update | LLM scoring NO | **ACTIF** |
| POLY_CONVERGENCE_STRAT | signal:wallet_convergence + signal:resolution_parsed | Convergence wallet | **ACTIF** |
| POLY_NEWS_STRAT | news:high_impact + feed:price_update | Réaction news | **ACTIF** |

---

## Stratégies ZOMBIE (actives mais ne produisant jamais de trade:signal)

| Stratégie | Raison | Tag |
|-----------|--------|-----|
| POLY_WEATHER_ARB | Active mais dépend de marchés météo Polymarket rares ou inexistants dans les 20 marchés actifs | [DÉDUIT] |
| POLY_CONVERGENCE_STRAT | Active mais wallet_feed + wallet_tracker DISABLED → jamais de `signal:wallet_convergence` | [OBSERVÉ] |
| POLY_NEWS_STRAT | Active mais consomme `news:high_impact` — producteur inconnu (pas de NEWS_FEED POLY interne) | [DÉDUIT] |
| POLY_OPP_SCORER | Active mais dépend de `signal:resolution_parsed` — market_analyst peut ne pas avoir été appelé | [DÉDUIT] |
| POLY_NO_SCANNER | Active mais même dépendance resolution_parsed | [DÉDUIT] |

**Conclusion** : 5 stratégies sont actives sur 9, mais **aucune n'a produit de trade:signal en 1.5 jours**. Les 4 stratégies DISABLED n'ont évidemment pas pu produire non plus. Le pipeline est entièrement stérile. [OBSERVÉ]

---

## Collisions state files (multi-writers potentiels)

| Fichier | Écrivains | Risque | Tag |
|---------|-----------|--------|-----|
| `risk/global_risk_state.json` | poly_global_risk_guard + orchestrateur (nightly) | FAIBLE — orchestrateur lit seulement | [DÉDUIT] |
| `orchestrator/heartbeat_state.json` | poly_heartbeat (seul writer) | AUCUN | [OBSERVÉ] |
| `evaluation/strategy_scores.json` | poly_performance_logger + poly_strategy_evaluator | MOYEN — 2 writers potentiels | [DÉDUIT] |
| `trading/paper_trades_log.jsonl` | poly_paper_execution_engine (seul writer, append) | AUCUN | [OBSERVÉ] |

**Note** : Le PolyDataStore utilise des écritures atomiques (tmp→rename), ce qui atténue les risques de corruption. [OBSERVÉ]
