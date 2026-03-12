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
