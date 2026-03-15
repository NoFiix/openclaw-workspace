# trigger_matrix.md — Matrice des déclencheurs

**Date** : 2026-03-15
**Scope** : Tous les triggers (cron, PM2, pollers, scheduler, bus, manuels)

---

## Résumé exécutif

L'environnement OpenClaw a **4 mécanismes de déclenchement** : cron (8 entrées + 2 @reboot), PM2 (2 process), pollers Docker (2 daemons), et AgentScheduler Python (21 agents). Au total, **55+ triggers** actifs. Les risques principaux sont : double exécution bus_cleanup (C-08), absence de supervision des daemons @reboot, et dépendance critique du container Docker pour 80% des triggers. [OBSERVÉ]

---

## Matrice complète

### Cron jobs (host)

| Déclencheur | Type | Fréquence | Déclenche | Dépendances | Si échoue | Tag |
|-------------|------|-----------|-----------|-------------|-----------|-----|
| `0 7-23 * * *` hourly_scraper.js | Cron | 17×/jour | Scraping RSS + draft IA | Container Docker, ANTHROPIC_API_KEY | Draft manquant pour 1h, aucune alerte | [OBSERVÉ] |
| `15 19 * * *` scraper.js | Cron | 1×/jour | Scraping quotidien + sélection Telegram | Container Docker, ANTHROPIC_API_KEY | Pas de sélection quotidienne, aucune alerte | [OBSERVÉ] |
| `0 3 * * *` bus_rotation.js | Cron | 1×/jour | Rotation bus JSONL trading | Container Docker | Bus non rotaté, croissance | [OBSERVÉ] |
| `30 3 * * *` bus_cleanup_trading.js | Cron | 1×/jour | Nettoyage bus trading | Container Docker | Bus non nettoyé | [OBSERVÉ] |
| `0 2 * * *` bus_cleanup_trading.js | Cron | 1×/jour | **DOUBLON** de bus_cleanup (C-08) | Container Docker | Idem — idempotent | [OBSERVÉ] |
| `*/15 * * * *` run_watchdog.sh | Cron | 96×/jour | SYSTEM_WATCHDOG health check | Container Docker | Monitoring aveugle — SPOF critique | [OBSERVÉ] |
| `*/30 * * * *` check_watchdog_heartbeat.sh | Cron | 48×/jour | Vérifie que le watchdog tourne | Fichier heartbeat | Log CRIT si heartbeat stale (fix récent) | [OBSERVÉ] |
| `0 4 * * *` rotate_poller_log.sh | Cron | 1×/jour | Rotation poller.log | Fichier poller.log | Log non rotaté (fix récent) | [OBSERVÉ] |

### Cron @reboot (daemons)

| Déclencheur | Type | Fréquence | Déclenche | Dépendances | Si échoue | Tag |
|-------------|------|-----------|-----------|-------------|-----------|-----|
| `@reboot +30s` trading/poller.js | Daemon | Boot | Trading poller (boucle ~1s, 24 agents) | Container Docker | **Tout le Trading Factory down**, pas de restart auto post-boot | [OBSERVÉ] |
| `@reboot +35s` poller.js | Daemon | Boot | Content poller Telegram (boucle 2s) | Container Docker | **Publication Content down**, pas de restart auto post-boot | [OBSERVÉ] |

### PM2 processes (host)

| Déclencheur | Type | Fréquence | Déclenche | Dépendances | Si échoue | Tag |
|-------------|------|-----------|-----------|-------------|-----------|-----|
| PM2 `dashboard-api` | Process | Continu | Express.js API :3001 | Node.js, .env | Dashboard inaccessible, PM2 restart auto | [OBSERVÉ] |
| PM2 `poly-orchestrator` | Process | Continu | Python orchestrator (tick 2s, 21 agents) | Python .venv, .env | **Tout POLY_FACTORY down**, PM2 restart auto | [OBSERVÉ] |

### AgentScheduler Python (dans poly-orchestrator)

| Agent | Fréquence | Déclenche | Dépendances | Si échoue | Tag |
|-------|-----------|-----------|-------------|-----------|-----|
| ConnectorPolymarket | 300s | Refresh marchés Polymarket | Gamma API (public) | Marchés stale | [OBSERVÉ] |
| PolyBinanceFeed | 30s | Prix crypto (BTC, ETH) | Binance REST API | Prix stale, stratégies bloquées | [OBSERVÉ] |
| PolyNoaaFeed | 120s | Prévisions météo | NOAA API (public) | Weather_arb sans données | [OBSERVÉ] |
| PolyWalletFeed | 600s | Balance wallet | Polygon RPC | Balance stale | [OBSERVÉ] |
| PolyMarketStructureAnalyzer | 30s | Analyse spread/depth | Bus feed events | Analyse stale | [OBSERVÉ] |
| PolyBinanceSignals | 10s | Signaux techniques crypto | Bus feed events | Signaux techniques absents | [OBSERVÉ] |
| PolyWalletTracker | 60s | Tracking wallet | Bus feed events | — | [OBSERVÉ] |
| PolyDataValidator | 10s | Validation données | Bus feed events | Données non validées | [OBSERVÉ] |
| PolyArbScanner | 5s | Scanner arbitrage | Marchés + prix | Signaux arb manquants | [OBSERVÉ] |
| PolyWeatherArb | 60s | Arbitrage météo | NOAA + marchés | Signaux météo manquants | [OBSERVÉ] |
| PolyLatencyArb | 5s | Arbitrage latence | Prix Binance | Signaux latence manquants | [OBSERVÉ] |
| PolyBrownianSniper | 5s | Sniper mouvement brownien | Prix | Signaux brownien manquants | [OBSERVÉ] |
| PolyPairCost | 5s | Analyse coûts paires | Marchés + prix | — | [OBSERVÉ] |
| PolyOppScorer | 30s | Scoring opportunités (LLM) | Marchés, ANTHROPIC_API_KEY | Scores absents | [OBSERVÉ] |
| PolyNoScanner | 30s | Scanner marchés "No" (LLM) | Marchés, ANTHROPIC_API_KEY | Signaux "No" manquants | [OBSERVÉ] |
| PolyConvergenceStrat | 30s | Convergence stratégie | Marchés + données | Signaux convergence manquants | [OBSERVÉ] |
| PolyNewsStrat | 30s | News stratégie | **news:high_impact (ABSENT C-12)** | Stratégie zombie | [OBSERVÉ] |
| PolyExecutionRouter | 2s | Routage signaux → paper/live | Bus trade:signal | Trades non exécutés | [OBSERVÉ] |
| PolyPaperExecutionEngine | 2s | Exécution paper trades | Bus execute:paper | Trades paper non enregistrés | [OBSERVÉ] |
| PolyHeartbeat | 300s | Monitoring liveness agents | Tous les agents | Agents stale non détectés | [OBSERVÉ] |
| PolySystemMonitor | 300s | Health check global | State files | Santé non rapportée | [OBSERVÉ] |

### Bus events (déclencheurs asynchrones)

| Event | Producteur | Consommateur | Fréquence | Si absent | Tag |
|-------|-----------|-------------|-----------|-----------|-----|
| `trade:signal` (POLY) | 5 stratégies actives | PolyExecutionRouter | On-signal | 0 trades (situation actuelle pre-fix) | [OBSERVÉ] |
| `execute:paper` (POLY) | PolyExecutionRouter | PolyPaperExecutionEngine | On-signal | Trades non exécutés | [OBSERVÉ] |
| `risk:kill_switch` (POLY) | PolyKillSwitch | Tous agents | On-trip | Agents continuent malgré danger | [OBSERVÉ] |
| `system:agent_disabled` (POLY) | PolyHeartbeat | PolySystemMonitor | On-event | Agents disabled non signalés | [OBSERVÉ] |
| `news:high_impact` (POLY) | **AUCUN** (C-12) | PolyNewsStrat | Jamais | Stratégie zombie | [OBSERVÉ] |

---

## Déclencheurs orphelins

| Déclencheur | Problème | Sévérité | Tag |
|-------------|----------|----------|-----|
| `0 2 * * *` bus_cleanup_trading.js | Doublon de `30 3 * * *` — même script exécuté 2× (C-08) | LOW | [OBSERVÉ] |
| PolyNewsStrat (30s) | Attend `news:high_impact` qui n'est jamais produit — CPU gaspillé | MEDIUM | [OBSERVÉ] |
| PREDICTOR (JS, 60s) | Produit des prédictions sans consommateur — 11k runs inutiles | LOW | [OBSERVÉ] |
| cleanup.js | Script existant mais **pas dans le crontab** — mémoire agents non purgée | MEDIUM | [OBSERVÉ] |
| youtube_analyzer.js | Script existant mais **pas dans le crontab** — dormant | LOW | [OBSERVÉ] |
| router.js | Module existant mais **importé par personne** — code mort | LOW | [OBSERVÉ] |

---

## Dépendances temporelles

### Séquences critiques au boot

```
BOOT
  +0s   Docker daemon démarre containers
  +30s  @reboot: trading/poller.js (Docker exec -d)
  +35s  @reboot: poller.js content (Docker exec -d)
  +auto PM2: poly-orchestrator redémarre
  +auto PM2: dashboard-api redémarre
```

**Risque** : Si Docker met > 30s à démarrer, les @reboot échouent silencieusement. `sleep 30` est une estimation, pas une vérification. [DÉDUIT]

### Séquences quotidiennes implicites

```
02:00  bus_cleanup_trading.js (1er passage — doublon)
03:00  bus_rotation.js
03:30  bus_cleanup_trading.js (2ème passage)
04:00  rotate_poller_log.sh (fix récent)
07:00  hourly_scraper.js démarre
08:00  SYSTEM_WATCHDOG rapport quotidien
08:00  GLOBAL_TOKEN_ANALYST (Lun + Jeu)
19:15  scraper.js quotidien
20:00  GLOBAL_TOKEN_TRACKER rapport quotidien
20:00  POLY_TRADING_PUBLISHER rapport quotidien
```

**Dépendance implicite** : bus_rotation (03:00) DOIT se faire avant la reprise des agents le matin, sinon le bus est non-rotaté. Pas de vérification que rotation a réussi. [DÉDUIT]

**Dépendance implicite** : GLOBAL_TOKEN_ANALYST (08:00) dépend de GLOBAL_TOKEN_TRACKER (20:00 veille) pour avoir des données fraîches dans token_summary.json. Si Tracker échoue, Analyst analyse des données stale. [DÉDUIT]
