# env_inventory.md — Inventaire de l'environnement

**Date** : 2026-03-15
**Méthode** : observation directe (commandes système)

---

## Serveur

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Hostname | srv1425899 | [OBSERVÉ] |
| OS | Ubuntu 22.04.5 LTS (jammy) | [OBSERVÉ] |
| Kernel | 5.15.0-171-generic x86_64 | [OBSERVÉ] |
| RAM | 7.8 Go (1.6 Go used, 5.8 Go available) | [OBSERVÉ] |
| Disque | 97 Go (17 Go used, 81 Go free, 17%) | [OBSERVÉ] |
| Swap | 0 (aucun swap configuré) | [OBSERVÉ] |
| Utilisateurs | `openclawadmin` (principal), `ubuntu` (legacy) | [OBSERVÉ] |

---

## Runtime

| Composant | Version | Emplacement | Tag |
|-----------|---------|-------------|-----|
| Node.js | v22.22.1 | `/home/openclawadmin/.nvm/versions/node/v22.22.1/bin/node` | [OBSERVÉ] |
| Python (system) | 3.10.12 | `/usr/bin/python3` | [OBSERVÉ] |
| Python (venv) | 3.11.15 | `POLY_FACTORY/.venv/bin/python` | [DÉDUIT] ps output |
| PM2 | 6.0.14 | global npm | [OBSERVÉ] |
| Docker | 29.2.1 | system | [OBSERVÉ] |
| npm | (via nvm) | global | [OBSERVÉ] |

---

## Composants applicatifs

### TYPE_1 — Critique (trading/argent)

| Composant | Technologie | Processus | État | Tag |
|-----------|------------|-----------|------|-----|
| POLY_FACTORY | Python 3.11 | PM2 `poly-orchestrator` | online, 98% CPU | [OBSERVÉ] |
| Trading Factory (JS) | Node.js | PM2 `trading-poller` + cron poller | online | [OBSERVÉ] |
| Execution Router | Python (dans poly-orchestrator) | — | paper mode | [OBSERVÉ] |

### TYPE_2 — Important (opérations)

| Composant | Technologie | Processus | État | Tag |
|-----------|------------|-----------|------|-----|
| Dashboard API | Node.js | PM2 `dashboard-api` | online, port 3001 | [OBSERVÉ] |
| OpenClaw Gateway | Node.js (Docker) | Docker container | healthy, ports 18789-18790 | [OBSERVÉ] |
| SYSTEM_WATCHDOG | Node.js (cron) | cron */15min | actif | [OBSERVÉ] |

### TYPE_3 — Support

| Composant | Technologie | Processus | État | Tag |
|-----------|------------|-----------|------|-----|
| hourly_scraper | Node.js (cron) | cron 7-23h | actif | [OBSERVÉ] |
| daily_scraper | Node.js (cron) | cron 19:15 | actif | [OBSERVÉ] |
| bus_rotation | Node.js (cron) | cron 3:00 | actif | [OBSERVÉ] |
| bus_cleanup | Node.js (cron) | cron 3:30 + dim 2:00 | actif | [OBSERVÉ] |
| content poller | Node.js (cron @reboot) | Docker exec | [SUPPOSÉ] actif | [DÉDUIT] |

### TYPE_4 — Legacy/dormant

| Composant | Technologie | État | Tag |
|-----------|------------|------|-----|
| 25 JS trading agents | Node.js | schedule-based via poller.js | [OBSERVÉ] |
| _deferred/ agents | Node.js | inactifs | [DÉDUIT] nom du dossier |

---

## Agents JS Trading Factory (skills_custom/trading/)

| Agent | Type | Tag |
|-------|------|-----|
| BINANCE_PRICE_FEED | Data feed | [OBSERVÉ] |
| GLOBAL_TOKEN_ANALYST | Analysis | [OBSERVÉ] |
| GLOBAL_TOKEN_TRACKER | Tracking | [OBSERVÉ] |
| KILL_SWITCH_GUARDIAN | Risk | [OBSERVÉ] |
| MARKET_EYE | Monitoring | [OBSERVÉ] |
| NEWS_FEED | Data feed | [OBSERVÉ] |
| NEWS_SCORING | Analysis | [OBSERVÉ] |
| PAPER_EXECUTOR | Execution | [OBSERVÉ] |
| PERFORMANCE_ANALYST | Evaluation | [OBSERVÉ] |
| POLICY_ENGINE | Risk | [OBSERVÉ] |
| POLY_TRADING_PUBLISHER | Bridge | [OBSERVÉ] |
| PREDICTOR | Strategy | [OBSERVÉ] |
| REGIME_DETECTOR | Analysis | [OBSERVÉ] |
| RISK_MANAGER | Risk | [OBSERVÉ] |
| STRATEGY_GATEKEEPER | Risk | [OBSERVÉ] |
| STRATEGY_RESEARCHER | Research | [OBSERVÉ] |
| SYSTEM_WATCHDOG | Monitoring | [OBSERVÉ] |
| TESTNET_EXECUTOR | Execution | [OBSERVÉ] |
| TRADE_GENERATOR | Strategy | [OBSERVÉ] |
| TRADE_STRATEGY_TUNER | Optimization | [OBSERVÉ] |
| TRADING_ORCHESTRATOR | Orchestration | [OBSERVÉ] |
| TRADING_PUBLISHER | Publication | [OBSERVÉ] |
| WHALE_ANALYZER | Analysis | [OBSERVÉ] |
| WHALE_FEED | Data feed | [OBSERVÉ] |

---

## Agents POLY_FACTORY (Python)

| Agent | Rôle | Intervalle | Tag |
|-------|------|-----------|-----|
| ConnectorPolymarket | Feed Polymarket | 300s | [OBSERVÉ] |
| PolyBinanceFeed | Feed Binance | 30s | [OBSERVÉ] |
| PolyNoaaFeed | Feed NOAA | 120s | [OBSERVÉ] |
| PolyWalletFeed | Feed wallet | 600s | [OBSERVÉ] |
| PolyMarketStructureAnalyzer | Signal C2 | 30s | [OBSERVÉ] |
| PolyBinanceSignals | Signal C2 | 10s | [OBSERVÉ] |
| PolyWalletTracker | Signal C2 | 60s | [OBSERVÉ] |
| PolyDataValidator | Validation | 10s | [OBSERVÉ] |
| PolyArbScanner | Strategy | 5s | [OBSERVÉ] |
| PolyWeatherArb | Strategy | 60s | [OBSERVÉ] |
| PolyLatencyArb | Strategy | 5s | [OBSERVÉ] |
| PolyBrownianSniper | Strategy | 5s | [OBSERVÉ] |
| PolyPairCost | Strategy | 5s | [OBSERVÉ] |
| PolyOppScorer | Strategy | 30s | [OBSERVÉ] |
| PolyNoScanner | Strategy | 30s | [OBSERVÉ] |
| PolyConvergenceStrat | Strategy | 30s | [OBSERVÉ] |
| PolyNewsStrat | Strategy | 30s | [OBSERVÉ] |
| PolyExecutionRouter | Execution | 2s | [OBSERVÉ] |
| PolyPaperExecutionEngine | Execution | 2s | [OBSERVÉ] |
| PolyHeartbeat | System | 300s | [OBSERVÉ] |
| PolySystemMonitor | System | 300s | [OBSERVÉ] |
