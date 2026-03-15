# agents.md — Inventaire des agents Trading Factory

**Date** : 2026-03-15
**Scope** : 24 agents dans `skills_custom/trading/`

---

## Agents DATA FEEDS (4)

### 1. BINANCE_PRICE_FEED
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Fetch prix spot Binance (BTC/ETH/BNB), tickers + klines 1m | [OBSERVÉ] |
| Criticité | **CORE** — sans lui, aucun indicateur, aucun trade | [DÉDUIT] |
| Inputs | Binance REST `/api/v3/ticker/24hr` + `/api/v3/klines` | [OBSERVÉ] |
| Outputs | `trading.raw.market.ticker` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 10s | [OBSERVÉ] |
| State | Aucun fichier persisté | [OBSERVÉ] |
| Timeout | 8s par requête | [OBSERVÉ] |
| Retry | Aucun (abort on timeout) | [OBSERVÉ] |
| Statut | **ACTIF** — 0 erreurs | [OBSERVÉ] |

### 2. MARKET_EYE
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Calcul RSI/BB/MACD/ATR/Volume Z-score sur 3 timeframes (5m, 1h, 4h) | [OBSERVÉ] |
| Criticité | **CORE** — fournit les features à toute la chaîne | [DÉDUIT] |
| Inputs | Binance REST `/api/v3/klines` (fetch direct, pas bus) | [OBSERVÉ] |
| Outputs | `trading.intel.market.features` (1 event/symbol/timeframe) | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 15s | [OBSERVÉ] |
| State | Aucun | [OBSERVÉ] |
| Timeout | 8s | [OBSERVÉ] |
| Runs/Errors | 32 339 / 0 | [OBSERVÉ] |
| Statut | **ACTIF** — healthy | [OBSERVÉ] |

### 3. NEWS_FEED
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Agrège 6 RSS + CryptoPanic + SEC EDGAR + Fear&Greed Index | [OBSERVÉ] |
| Criticité | SUPPORT — enrichit les signaux mais pas bloquant | [DÉDUIT] |
| Inputs | RSS feeds, CryptoPanic API, SEC EDGAR, F&G API | [OBSERVÉ] |
| Outputs | `trading.raw.news.article`, `trading.raw.social.post` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 300s | [OBSERVÉ] |
| Dedup | SHA256 hash, sliding window 1000 | [OBSERVÉ] |
| Timeout | 10s | [OBSERVÉ] |
| Runs/Errors | 1 449 / 0 | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 4. WHALE_FEED
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Collecte whale transfers ETH/USDT/USDC/WBTC via Etherscan v2 | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Inputs | Etherscan v2 (txlist + tokentx), CoinGecko (prix USD) | [OBSERVÉ] |
| Outputs | `trading.raw.whale.transfer` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 300s + jitter 15s | [OBSERVÉ] |
| Rate limit | 250ms entre appels ERC20 | [OBSERVÉ] |
| Dedup | tx_hash TTL 2h | [OBSERVÉ] |
| Runs/Errors | 1 449 / **79 erreurs** | [OBSERVÉ] |
| Statut | **ACTIF** — dégradé (79 erreurs = rate limit Etherscan) | [DÉDUIT] |

---

## Agents SIGNAL GENERATION (3)

### 5. WHALE_ANALYZER
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Classifie flux whale (TO_EXCHANGE, FROM_EXCHANGE, etc.), score [-1,+1] sur 6h | [OBSERVÉ] |
| Criticité | SUPPORT — consultatif uniquement | [OBSERVÉ] |
| Inputs | `trading.raw.whale.transfer` (bus), `configs/exchange_addresses.json` | [OBSERVÉ] |
| Outputs | `trading.intel.whale.signal` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 300s + jitter 60s | [OBSERVÉ] |
| Runs/Errors | 1 454 / 0 | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 6. PREDICTOR
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Prédit direction (BULL/BEAR/NEUTRAL) via scoring pondéré RSI+BB+MACD+Volume | [OBSERVÉ] |
| Criticité | SUPPORT — enrichit TRADE_GENERATOR | [DÉDUIT] |
| Inputs | `trading.intel.market.features` | [OBSERVÉ] |
| Outputs | `trading.intel.prediction` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 60s | [OBSERVÉ] |
| Runs/Errors | 11 093 / 0 | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 7. REGIME_DETECTOR
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Identifie régime de marché (TREND_UP/DOWN/RANGE/PANIC/EUPHORIA/VOLATILE) + whale_context | [OBSERVÉ] |
| Criticité | **CORE** — conditionne les stratégies dans TRADE_GENERATOR | [DÉDUIT] |
| Inputs | `trading.intel.market.features`, `trading.intel.whale.signal` | [OBSERVÉ] |
| Outputs | `trading.intel.regime` (v2 avec whale_context) | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 60s | [OBSERVÉ] |
| Runs/Errors | 10 093 / 0 | [OBSERVÉ] |
| Statut | **ACTIF** — mais `regime_current.json` = null [OBSERVÉ] |

---

## Agents INTELLIGENCE (2)

### 8. NEWS_SCORING
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Score urgence/fiabilité/relevance de chaque news via Haiku. Alerte Telegram si urgency ≥9 | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| Inputs | `trading.raw.news.article`, `trading.raw.social.post` | [OBSERVÉ] |
| Outputs | `trading.intel.news.event` (si urgency ≥3), `trading.ops.alert` (si urgency ≥9 ET reliability ≥0.7) | [OBSERVÉ] |
| LLM | **Haiku** — 400 tokens max output, budget 25s/run | [OBSERVÉ] |
| Coût estimé | ~$0.0007/news, **$0.80/jour** (61% du budget LLM total) | [OBSERVÉ] |
| Schedule | 300s | [OBSERVÉ] |
| Statut | **ACTIF** — 7 303 appels LLM | [OBSERVÉ] |

### 9. TRADE_GENERATOR
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Moteur stratégique : lit features + regime + news, appelle Haiku si signal détecté (filtre pré-Haiku hasSignal), génère proposals | [OBSERVÉ] |
| Criticité | **CORE** — seul producteur de signaux de trade | [DÉDUIT] |
| Inputs | `trading.intel.market.features`, `trading.intel.regime`, `trading.intel.news.event`, `learning/strategy_candidates.json`, `learning/strategy_performance.json` | [OBSERVÉ] |
| Outputs | `trading.strategy.trade.proposal` | [OBSERVÉ] |
| LLM | **Haiku** — 600 tokens max output, cooldown 30min/symbol | [OBSERVÉ] |
| Coût estimé | ~$0.003/appel, **$0.49/jour** (38% du budget) | [OBSERVÉ] |
| Schedule | 300s | [OBSERVÉ] |
| Runs/Errors | 2 343 / 0 | [OBSERVÉ] |
| Statut | **ACTIF** — stratégie Momentum seule active | [OBSERVÉ] |

---

## Agents RISK & POLICY (3)

### 10. RISK_MANAGER
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Chaîne 7 filtres : confidence, R/R, stop-loss, overlap, daily loss. Sizing Kelly. | [OBSERVÉ] |
| Criticité | **CORE** — gate obligatoire avant exécution | [DÉDUIT] |
| Inputs | `trading.strategy.trade.proposal` | [OBSERVÉ] |
| Outputs | `trading.strategy.order.plan` (validé), `trading.strategy.block` (rejeté) | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 60s | [OBSERVÉ] |
| State critique | Lit `exec/positions.json`, `exec/daily_pnl.json` | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 11. POLICY_ENGINE
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Règles système : asset whitelist, notional thresholds, time windows. APPROVED / BLOCKED / HUMAN_APPROVAL_REQUIRED | [OBSERVÉ] |
| Criticité | **CORE** — gate obligatoire | [DÉDUIT] |
| Inputs | `trading.strategy.order.plan` | [OBSERVÉ] |
| Outputs | `trading.strategy.policy.decision` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 30s | [OBSERVÉ] |
| Config | `configs/POLICY_ENGINE.config.json` (env=paper, 3 assets, 4 strategies) | [OBSERVÉ] |
| Audit | `memory/policy_decisions.jsonl` | [OBSERVÉ] |
| Runs/Errors | 10 757 / 0 | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 12. KILL_SWITCH_GUARDIAN
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Coupe tout si daily loss >3%, 3+ erreurs executor, data quality degraded >15min, exchange down >5min | [OBSERVÉ] |
| Criticité | **CORE** — sécurité capitale | [DÉDUIT] |
| Inputs | Lit bus (error counts, data quality), `exec/daily_pnl_testnet.json` | [OBSERVÉ] |
| Outputs | `trading.ops.killswitch.state`, `trading.ops.alert`, `exec/killswitch.json` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 60s | [OBSERVÉ] |
| Runs/Errors | 23 645 / **27 399 erreurs** ⚠️ | [OBSERVÉ] |
| Statut | **ACTIF mais DÉGRADÉ** — taux d'erreur 115% | [OBSERVÉ] |

---

## Agents ORCHESTRATION & EXÉCUTION (3)

### 13. TRADING_ORCHESTRATOR
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | State machine : corrèle order.plan + policy.decision → PENDING_POLICY → APPROVED/BLOCKED/EXPIRED → order.submit | [OBSERVÉ] |
| Criticité | **CORE** | [DÉDUIT] |
| Inputs | `trading.strategy.order.plan`, `trading.strategy.policy.decision` | [OBSERVÉ] |
| Outputs | `trading.exec.order.submit` | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 10s | [OBSERVÉ] |
| State critique | `memory/pipeline_state.json` (200 active + 100 terminal) | [OBSERVÉ] |
| TTL | 10 min (EXPIRED si pas approuvé) | [OBSERVÉ] |
| Runs/Errors | 19 047 / 0 | [OBSERVÉ] |
| Constat | 95 ordres HUMAN_APPROVAL_REQUIRED → tous EXPIRED | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 14. PAPER_EXECUTOR
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Simule exécution paper : open/close positions, TP/SL, slippage 10 bps | [OBSERVÉ] |
| Criticité | SUPPORT (mode paper) | [DÉDUIT] |
| Inputs | `trading.strategy.order.plan` | [OBSERVÉ] |
| Outputs | `trading.exec.trade.ledger`, `trading.exec.position.snapshot` | [OBSERVÉ] |
| State critique | `exec/positions.json`, `exec/daily_pnl.json` | [OBSERVÉ] |
| Statut | **ACTIF** | [DÉDUIT] |

### 15. TESTNET_EXECUTOR
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Exécution réelle Binance Testnet : MARKET + OCO (TP+SL). Signe HMAC-SHA256. | [OBSERVÉ] |
| Criticité | **CORE** (en mode testnet) | [DÉDUIT] |
| Inputs | `trading.exec.order.submit` | [OBSERVÉ] |
| Outputs | `trading.exec.trade.ledger`, `trading.exec.position.snapshot`, `trading.risk.kill_switch` | [OBSERVÉ] |
| State critique | `exec/positions_testnet.json`, `exec/daily_pnl_testnet.json`, `exec/killswitch.json` | [OBSERVÉ] |
| External API | Binance Testnet REST (order, oco, exchangeInfo, ticker/price) | [OBSERVÉ] |
| Timeout | 10s | [OBSERVÉ] |
| Statut | **ACTIF** — 4 trades exécutés avec succès | [OBSERVÉ] |

---

## Agents PUBLICATION (3)

### 16. TRADING_PUBLISHER
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Publie trades (open/close), bilans daily/weekly, contenu éducatif sur Telegram | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| LLM | **Haiku** — 180 tokens max (ligne Setup uniquement) | [OBSERVÉ] |
| Schedule | 60s | [OBSERVÉ] |
| Statut | **ACTIF** | [DÉDUIT] |

### 17. GLOBAL_TOKEN_TRACKER
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Agrège token_costs.jsonl (trading + POLY_FACTORY), bilan Telegram 20h UTC | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 3600s (report 1×/jour) | [OBSERVÉ] |
| Lit POLY_FACTORY | `POLY_FACTORY/state/llm/token_costs.jsonl` — **cross-système** | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 18. GLOBAL_TOKEN_ANALYST
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Analyse coûts tokens via Sonnet, propose optimisations (lundi + jeudi 8h UTC) | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| LLM | **Sonnet** — 1000 tokens max output | [OBSERVÉ] |
| Schedule | 86400s (gate lundi/jeudi 8h) | [OBSERVÉ] |
| Statut | **ACTIF** | [DÉDUIT] |

---

## Agents LEARNING & OPTIMISATION (4)

### 19. PERFORMANCE_ANALYST
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Calcul métriques : win_rate, PnL, Sharpe, drawdown, expectancy. 5 fichiers JSON. | [OBSERVÉ] |
| Criticité | SUPPORT (mais critique pour STRATEGY_GATEKEEPER et TUNER) | [DÉDUIT] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 3600s | [OBSERVÉ] |
| State écrits (5) | `learning/strategy_performance.json`, `learning/asset_performance.json`, `learning/regime_performance_matrix.json`, `learning/daily_performance.json`, `learning/global_performance.json` | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 20. STRATEGY_GATEKEEPER
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Active/désactive stratégies (score ≥0.60=active, 0.40-0.59=testing, <0.40=rejected) | [OBSERVÉ] |
| Criticité | SUPPORT | [DÉDUIT] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | 3600s | [OBSERVÉ] |
| Min trades | 20 pour décision | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 21. STRATEGY_RESEARCHER
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Scrape Reddit (r/algotrading, r/CryptoMarkets, r/trading), extrait stratégies via Sonnet | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| LLM | **Sonnet** — 1500 tokens max output | [OBSERVÉ] |
| Coût | ~$0.01/jour | [OBSERVÉ] |
| Schedule | 86400s (1×/jour, gate last_run_date) | [OBSERVÉ] |
| Statut | **ACTIF** — 12 appels, 1 candidate trouvée (Mean Reversion IBS) | [OBSERVÉ] |

### 22. TRADE_STRATEGY_TUNER
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Optimisation paramètres : 1 param à la fois, delta borné, rollback auto, anti-oscillation | [OBSERVÉ] |
| Criticité | EXPERIMENTAL | [DÉDUIT] |
| LLM | **Sonnet** — 1024 tokens max output | [OBSERVÉ] |
| Schedule | 604800s (1×/semaine, gate MIN_TRADES=30) | [OBSERVÉ] |
| Constat | 4 trades seulement → pas encore déclenché (besoin 30) | [DÉDUIT] |
| Statut | **DORMANT** (attend 30 trades) | [DÉDUIT] |

---

## Agents MONITORING (2)

### 23. SYSTEM_WATCHDOG
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Health monitoring : 33 nœuds (21 trading + 2 global + 4 content scripts + 6 CF agents), alertes Telegram | [OBSERVÉ] |
| Criticité | **CORE** — seul système de monitoring | [DÉDUIT] |
| LLM | Aucun | [OBSERVÉ] |
| Schedule | Cron */15min | [OBSERVÉ] |
| Incidents ouverts | 3 CRIT + 2 WARN | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] |

### 24. POLY_TRADING_PUBLISHER
| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Bridge POLY_FACTORY → Telegram : publie paper/live trades, bilans daily 20h, weekly dimanche | [OBSERVÉ] |
| Criticité | SUPPORT — pont entre POLY_FACTORY et notifications Telegram | [DÉDUIT] |
| LLM | [INCONNU] | |
| Lit POLY_FACTORY | `POLY_FACTORY/state/trading/paper_trades_log.jsonl`, `POLY_FACTORY/state/orchestrator/system_state.json` | [DÉDUIT] |
| Statut | **ACTIF** | [DÉDUIT] |

---

## Matrice de dépendances

| Agent | Dépend de | Fournit à |
|-------|-----------|-----------|
| BINANCE_PRICE_FEED | Binance API | MARKET_EYE (indirect) |
| MARKET_EYE | Binance API | PREDICTOR, REGIME_DETECTOR, TRADE_GENERATOR |
| NEWS_FEED | RSS, CryptoPanic, EDGAR, F&G | NEWS_SCORING |
| NEWS_SCORING | NEWS_FEED | TRADE_GENERATOR |
| WHALE_FEED | Etherscan, CoinGecko | WHALE_ANALYZER |
| WHALE_ANALYZER | WHALE_FEED | REGIME_DETECTOR |
| PREDICTOR | MARKET_EYE | (consommateur final) |
| REGIME_DETECTOR | MARKET_EYE, WHALE_ANALYZER | TRADE_GENERATOR |
| TRADE_GENERATOR | MARKET_EYE, REGIME_DETECTOR, NEWS_SCORING | RISK_MANAGER |
| RISK_MANAGER | TRADE_GENERATOR | POLICY_ENGINE, PAPER_EXECUTOR |
| POLICY_ENGINE | RISK_MANAGER | TRADING_ORCHESTRATOR |
| TRADING_ORCHESTRATOR | POLICY_ENGINE, RISK_MANAGER | TESTNET_EXECUTOR |
| TESTNET_EXECUTOR | TRADING_ORCHESTRATOR | PERFORMANCE_ANALYST, KILL_SWITCH_GUARDIAN |
| PAPER_EXECUTOR | RISK_MANAGER | PERFORMANCE_ANALYST |
| KILL_SWITCH_GUARDIAN | TESTNET_EXECUTOR (PnL) | Tout le système (HALT) |
| PERFORMANCE_ANALYST | TESTNET/PAPER_EXECUTOR | STRATEGY_GATEKEEPER, TRADE_STRATEGY_TUNER |
| STRATEGY_GATEKEEPER | PERFORMANCE_ANALYST | TRADE_GENERATOR (enable/disable) |
| TRADE_STRATEGY_TUNER | PERFORMANCE_ANALYST | TRADE_GENERATOR (params) |
| STRATEGY_RESEARCHER | Reddit | TRADE_GENERATOR (candidates) |
| TRADING_PUBLISHER | TESTNET_EXECUTOR, PERFORMANCE_ANALYST | Telegram (output) |
| GLOBAL_TOKEN_TRACKER | Tous les agents LLM | GLOBAL_TOKEN_ANALYST |
| GLOBAL_TOKEN_ANALYST | GLOBAL_TOKEN_TRACKER | Telegram (recommendations) |
| SYSTEM_WATCHDOG | Tous les agents (state files) | Telegram (alertes) |
| POLY_TRADING_PUBLISHER | POLY_FACTORY state files | Telegram (POLY trades) |

---

## Agents ORPHELINS

| Agent | Statut | Impact | Tag |
|-------|--------|--------|-----|
| PREDICTOR | Semi-orphelin | Publie `trading.intel.prediction` mais aucun consommateur identifié dans le code actuel. TRADE_GENERATOR lit features + regime + news, pas prediction. | [DÉDUIT] |

---

## Dead strategies (produites mais non utilisées)

| Stratégie | Source | Statut | Tag |
|-----------|--------|--------|-----|
| Mean Reversion IBS | STRATEGY_RESEARCHER (Reddit) | `candidate`, 0 test trades, découverte 2026-03-06 | [OBSERVÉ] |
| MeanReversion (builtin) | Hardcodé | Inactif — 1 seul trade ancien | [DÉDUIT] |
| Breakout (builtin) | Hardcodé | Jamais tradé | [DÉDUIT] |
| NewsTrading | Autorisé par POLICY_ENGINE | Jamais implémenté dans TRADE_GENERATOR | [DÉDUIT] |
