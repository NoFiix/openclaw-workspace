# Sprint Courant

## POLY-001 — Create POLY_DATA_STORE base structure

**Status** : done

---

## POLY-002 — Create POLY_AUDIT_LOG

**Status** : done

---

## POLY-003 — Create Event Bus

**Status** : done

---

## POLY-004 — Create POLY_MARKET_CONNECTOR (connector_polymarket)

**Status** : done

---

## POLY-005 — Create POLY_BINANCE_FEED

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `agents/poly_binance_feed.py`
- [x] Créer `tests/test_binance_feed.py`
- [x] Vérifier que les tests passent (24/24 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-006 — Create POLY_NOAA_FEED

**Status** : done

### Étapes
- [x] Créer `references/station_mapping.json` (6 stations)
- [x] Créer `agents/poly_noaa_feed.py`
- [x] Créer `tests/test_noaa_feed.py`
- [x] Vérifier que les tests passent (12/12 passed)
- [x] Vérifier que la suite complète passe (124/124 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-007 — Create POLY_WALLET_FEED

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `references/tracked_wallets.json` (10 wallets)
- [x] Créer `agents/poly_wallet_feed.py`
- [x] Créer `tests/test_wallet_feed.py`
- [x] Vérifier que les tests passent (24/24 passed)
- [x] Vérifier que la suite complète passe (148/148 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-008 — Create POLY_DATA_VALIDATOR

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `references/validation_rules.json`
- [x] Créer `agents/poly_data_validator.py`
- [x] Créer `tests/test_data_validator.py`
- [x] Vérifier que les tests passent (27/27 passed)
- [x] Vérifier que la suite complète passe (175/175 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-009 — Create POLY_BINANCE_SIGNALS

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `agents/poly_binance_signals.py`
- [x] Créer `tests/test_binance_signals.py`
- [x] Vérifier que les tests passent (20/20 passed)
- [x] Vérifier que la suite complète passe (195/195 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-010 — Create POLY_MARKET_STRUCTURE_ANALYZER

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Mettre à jour `core/poly_event_bus.py` (OVERWRITE_KEYS: signal:market_structure)
- [x] Créer `agents/poly_market_structure_analyzer.py`
- [x] Créer `tests/test_market_structure.py`
- [x] Vérifier que les tests passent (18/18 passed)
- [x] Vérifier que la suite complète passe (213/213 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-011 — Create POLY_WALLET_TRACKER

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `references/wallet_blacklist_rules.json`
- [x] Créer `agents/poly_wallet_tracker.py`
- [x] Créer `tests/test_wallet_tracker.py`
- [x] Vérifier que les tests passent (19/19 passed)
- [x] Vérifier que la suite complète passe (232/232 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-012 — Create POLY_MARKET_ANALYST

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `prompts/resolution_parser_prompt.txt`
- [x] Créer `agents/poly_market_analyst.py`
- [x] Créer `tests/test_market_analyst.py`
- [x] Vérifier que les tests passent (16/16 passed)
- [x] Vérifier que la suite complète passe (248/248 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-013 — Create POLY_BACKTEST_ENGINE

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `evaluation/poly_backtest_engine.py`
- [x] Créer `tests/test_backtest_engine.py`
- [x] Vérifier que les tests passent (21/21 passed)
- [x] Vérifier que la suite complète passe (269/269 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-014 — Create POLY_STRATEGY_REGISTRY

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `core/poly_strategy_registry.py`
- [x] Créer `tests/test_strategy_registry.py`
- [x] Vérifier que les tests passent (30/30 passed)
- [x] Vérifier que la suite complète passe (299/299 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-015 — Create POLY_STRATEGY_ACCOUNT

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `core/poly_strategy_account.py`
- [x] Créer `tests/test_strategy_account.py`
- [x] Vérifier que les tests passent (39/39 passed)
- [x] Vérifier que la suite complète passe (338/338 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-016 — Create POLY_KELLY_SIZER

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `risk/poly_kelly_sizer.py`
- [x] Créer `tests/test_kelly_sizer.py`
- [x] Vérifier que les tests passent (27/27 passed)
- [x] Vérifier que la suite complète passe (365/365 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-017 — Create POLY_PAPER_EXECUTION_ENGINE

**Status** : done

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `execution/poly_paper_execution_engine.py`
- [x] Créer `tests/test_paper_execution.py`
- [x] Vérifier que les tests passent (16/16 passed)
- [x] Vérifier que la suite complète passe (381/381 passed)
- [x] Vérifier `grep -r "py_clob_client\|py-clob-client" execution/poly_paper_execution_engine.py` → 0 résultats
- [x] Vérifier les critères d'acceptation

---

## POLY-018 — Create POLY_ORDER_SPLITTER

**Status** : done

### Plan
- `execution/poly_order_splitter.py` — pure utility class `PolyOrderSplitter`
- `split(size_eur, price_limit, depth_usd)` — core split, no I/O
- `split_from_market(size_eur, price_limit, market_id)` — reads depth from `state/feeds/market_structure.json` via PolyDataStore
- Algorithm: `max_tranche = clamp(depth_usd * 0.01, 1.0, 500.0)`, `n = clamp(ceil(size_eur / max_tranche), 1, 10)`
- No bus events, no audit — called synchronously by execution engines

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `execution/poly_order_splitter.py`
- [x] Créer `tests/test_order_splitter.py`
- [x] Vérifier que les tests passent (18/18 passed)
- [x] Vérifier que la suite complète passe (399/399 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-019 — Create POLY_ARB_SCANNER

**Status** : done

### Plan
- `strategies/poly_arb_scanner.py` — `PolyArbScanner` class; NO execution logic
- Consumes: `feed:price_update` + `signal:market_structure` (via bus poll)
- Emits: `trade:signal` with `direction=BUY_YES_AND_NO`, `signal_type=bundle_arb`
- Core logic: `yes_ask + no_ask < SUM_THRESHOLD (0.97)` AND `executability_score >= MIN_EXECUTABILITY (60)` → signal
- Confidence: `min(1.0, (SUM_THRESHOLD - ask_sum) / SUM_THRESHOLD)`
- `_market_structure` dict caches latest `signal:market_structure` payloads per market_id
- `run_once()` polls both topics, updates cache on market_structure events, checks arb on price events, acks all

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `strategies/poly_arb_scanner.py`
- [x] Créer `tests/test_arb_scanner.py`
- [x] Vérifier que les tests passent (26/26 passed)
- [x] Vérifier que la suite complète passe (425/425 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-020 — Create POLY_WEATHER_ARB

**Status** : done

### Plan
- `strategies/poly_weather_arb.py` — `PolyWeatherArb` class; NO execution logic
- `references/weather_market_mapping.json` — static config: station → markets → temperature buckets → market_id
- Consumes: `feed:price_update` (price cache) + `feed:noaa_update` (triggers check)
- Emits: `trade:signal` with `direction=BUY_YES`, `signal_type=weather_arb`
- Core logic: `noaa_confidence - yes_ask > EDGE_THRESHOLD (0.15)` AND `confidence >= MIN_NOAA_CONFIDENCE (0.70)` AND `data_status == VALID` → signal
- `_get_bucket(temp_f, buckets)` maps forecast temp to the matching bucket dict
- `_check_opportunity(station, noaa_payload)` → list of signals against current price cache
- `run_once()` processes price events first (earlier timestamp), then noaa; both are overwrite topics sorted by timestamp

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `references/weather_market_mapping.json`
- [x] Créer `strategies/poly_weather_arb.py`
- [x] Créer `tests/test_weather_arb.py`
- [x] Vérifier que les tests passent (33/33 passed)
- [x] Vérifier que la suite complète passe (458/458 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-021 — Create POLY_KILL_SWITCH

**Status** : done

### Plan
- `risk/poly_kill_switch.py` — `PolyKillSwitch` class; safety-critical, no bypasses
- State: `state/risk/kill_switch_status.json` — one entry per strategy
- **5 response levels**: OK → WARNING → PAUSE_DAILY → PAUSE_SESSION → STOP_STRATEGY
- `evaluate(strategy, account_id)` — checks in priority order:
  1. `current_drawdown_pct < -30%` → STOP_STRATEGY (permanent)
  2. `daily_pnl_pct < -5%` → PAUSE_DAILY (until midnight)
  3. `consecutive_losses >= 3` → PAUSE_DAILY (until midnight)
  4. `daily_pnl_pct < -4%` (80% of limit) → WARNING
  5. All clear → OK
  - Dedup guard: same level+reason already active → skip re-publishing bus event
- `record_trade_result(strategy, pnl)` — loss increments counter; win resets to 0
- `check_feed_health(strategy, account_id, feed_age_seconds)` — >300s → PAUSE_SESSION
- `check_pre_trade(strategy)` — fast cached check; returns `{allowed, level, reason}`
- `reset_daily(strategy)` — midnight: consecutive_losses=0, PAUSE_DAILY→OK (STOP_STRATEGY is permanent)
- `register(strategy, account_id)` — add to evaluation roster
- `run_once()` — tick: evaluate all registered strategies; returns list of triggered events
- Bus event: `risk:kill_switch` priority="high", payload matches §7 schema

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `risk/poly_kill_switch.py`
- [x] Créer `tests/test_kill_switch.py`
- [x] Vérifier que les tests passent (39/39 passed)
- [x] Vérifier que la suite complète passe (497/497 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-022 — Create POLY_RISK_GUARDIAN

**Status** : done

### Plan
- `risk/poly_risk_guardian.py` — `PolyRiskGuardian`; portfolio-level pre-trade guard
- State: `state/risk/portfolio_state.json` — `{open_positions: [...], last_updated}`
- **3 checks** (in priority order):
  1. `len(open_positions) < MAX_POSITIONS (5)` — position count
  2. `(sum_exposure + proposed) / total_capital <= MAX_EXPOSURE_PCT (0.80)` — exposure
  3. `(category_exposure + proposed) / total_capital <= MAX_CATEGORY_PCT (0.40)` — anti-correlation
- `check(proposed_size_eur, proposed_category, total_capital_eur) -> dict` — synchronous pre-trade; publishes `risk:portfolio_check` + audits
- `add_position(strategy, market_id, size_eur, category)` — called after execution
- `close_position(strategy, market_id)` — called after resolution
- `get_state() -> dict` — snapshot of current portfolio
- `blocked_by` field reports first failing check in priority order

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `risk/poly_risk_guardian.py`
- [x] Créer `tests/test_risk_guardian.py`
- [x] Vérifier que les tests passent (31/31 passed)
- [x] Vérifier que la suite complète passe (528/528 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-023 — Create POLY_GLOBAL_RISK_GUARD

**Status** : done

### Plan
- `risk/poly_global_risk_guard.py` — `PolyGlobalRiskGuard`; system-wide cumulative loss ceiling
- State: `state/risk/global_risk_state.json` — `{status, total_loss_eur, pct_used, registered_accounts, accounts_contributing, ...}`
- **4 status levels**:
  - NORMAL: total loss < 2 000€ — no action
  - ALERTE: 2 000–2 999€ — block_new_live_promotions
  - CRITIQUE: 3 000–3 999€ — block_new_live_promotions
  - ARRET_TOTAL: ≥ 4 000€ — halt_all_trading
- `register(account_id)` — add account to monitoring roster
- `evaluate() → dict` — reads all registered accounts, sums losses (only pnl.total < 0), updates status, publishes `risk:global_status` + audits **only on status change**
- `check_pre_trade() → dict` — fast cached check; `allowed=False` only at ARRET_TOTAL
- `get_state() → dict` — deep copy
- `run_once() → dict` — alias for evaluate(), called every 60s

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `risk/poly_global_risk_guard.py`
- [x] Créer `tests/test_global_risk_guard.py`
- [x] Vérifier que les tests passent (38/38 passed)
- [x] Vérifier que la suite complète passe (566/566 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-024 — Create POLY_CAPITAL_MANAGER

**Status** : done

### Plan
- `risk/poly_capital_manager.py` — `PolyCapitalManager`; account lifecycle + capital gate
- Gate DECIDES → Capital Manager EXECUTES (never creates live accounts without `promotion:approved`)
- `create_live_account(payload)` — archives existing paper account if present, creates fresh account, sets status "active", publishes `account:live_created`
- `check_capital(account_id, size_eur)` — filter 6 in 7-filter chain; `size_eur <= available` → allowed
- `recover_capital(strategy, account_id)` — stop_strategy → archive account, publish `account:live_closed`
- `run_once()` — polls `promotion:approved` + `risk:kill_switch`(stop_strategy); acks all

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `risk/poly_capital_manager.py`
- [x] Créer `tests/test_capital_manager.py`
- [x] Vérifier que les tests passent (33/33 passed)
- [x] Vérifier que la suite complète passe (599/599 passed)
- [x] Vérifier les critères d'acceptation

---

## POLY-025 — Create POLY_PERFORMANCE_LOGGER

**Status** : done

### Plan
- `evaluation/poly_performance_logger.py` — `PolyPerformanceLogger`; per-strategy P&L aggregation and milestone detection
- Maintains per-strategy P&L log: `state/trading/positions_by_strategy/{strategy}_pnl.jsonl`
- Writes to `dashboard-data/aggregates/poly_paper_stats.json` and `poly_live_stats.json`
- Milestones: [50, 100, 200, 500, 1000] trades — publishes `eval:milestone` on first crossing (dedup guard)
- 6 metrics: total_trades, win_rate, total_pnl, profit_factor, sharpe_ratio, max_drawdown_eur
- `log_trade(strategy, pnl, mode, trade_id, market_id)` — append resolved trade P&L
- `compute_metrics(strategy)` — pure computation, no side effects
- `update_stats(strategy, mode)` — compute + write + milestone check
- `get_stats(mode)` — read current dashboard stats
- `run_once(strategies, mode)` — batch update for all listed strategies

### Étapes
- [x] Lire le ticket et les documents de référence
- [x] Écrire le plan d'implémentation
- [x] Créer `evaluation/poly_performance_logger.py`
- [x] Créer `tests/test_performance_logger.py`
- [x] Vérifier que les tests passent (34/34 passed)
- [x] Vérifier que la suite complète passe (633/633 passed)
- [x] Vérifier les critères d'acceptation
