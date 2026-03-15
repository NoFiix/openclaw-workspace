# file_ownership.md — Propriété et accès aux dossiers

**Date** : 2026-03-15
**Scope** : Ownership, writers, readers, nettoyage pour chaque dossier important

---

## Résumé exécutif

La propriété des fichiers est globalement claire : chaque système écrit dans son propre dossier state. Les lectures croisées existent mais ne posent pas de risque. Le problème principal est l'**absence de nettoyage automatique** pour plusieurs dossiers critiques (bus trading 170 Mo, poller.log 48 Mo, trading_intel 72 Mo). [OBSERVÉ]

---

## ~/openclaw/workspace/state/trading/

| Sous-dossier | Owner | Writers autorisés | Readers | Nettoyage auto ? | Tag |
|-------------|-------|------------------|---------|-----------------|-----|
| `bus/` | Trading poller | 24 agents JS (via busWrite) | Agents JS (busRead), Dashboard API | ✅ bus_rotation.js (3h) + bus_cleanup (2h/3h30) | [OBSERVÉ] |
| `schedules/` | Trading poller | Trading poller (crée les .schedule.json) | SYSTEM_WATCHDOG, Dashboard API | ❌ Non | [OBSERVÉ] |
| `memory/` | Trading poller | Agents JS individuels | Dashboard API | ❌ Non | [OBSERVÉ] |
| `exec/` | Trading poller | TRADING_ORCHESTRATOR, PAPER_EXECUTOR, TESTNET_EXECUTOR | Dashboard API, SYSTEM_WATCHDOG | ❌ Non | [OBSERVÉ] |
| `learning/` | Trading poller | TOKEN_TRACKER, TOKEN_ANALYST, PERFORMANCE_ANALYST | Dashboard API | ❌ Non (token_costs.jsonl croissance illimitée) | [OBSERVÉ] |
| `risk/` | Trading poller | RISK_MANAGER, KILL_SWITCH_GUARDIAN | Dashboard API, SYSTEM_WATCHDOG | ❌ Non | [OBSERVÉ] |
| `runs/` | Trading poller | Tous les agents (log de chaque run) | SYSTEM_WATCHDOG | ❌ Non (~6 Mo) | [OBSERVÉ] |
| `audit/` | Trading cron | bus_rotation.js | — | ❌ Non | [OBSERVÉ] |
| `poller.log` | Trading poller | poller.js (append continu) | SYSTEM_WATCHDOG (mtime + tail) | ✅ rotate_poller_log.sh (4h, fix récent) | [OBSERVÉ] |

**Risques** :
- `bus/trading_intel_market_features.jsonl` = 72 Mo, croissance illimitée [OBSERVÉ]
- `poller.log` = 48 Mo → rotaté (fix appliqué) [OBSERVÉ]

---

## ~/openclaw/workspace/POLY_FACTORY/state/

| Sous-dossier | Owner | Writers autorisés | Readers externes | Nettoyage auto ? | Tag |
|-------------|-------|------------------|-----------------|-----------------|-----|
| `bus/` | poly-orchestrator | poly_event_bus.py (tous agents) | Dashboard API | ✅ compact() (auto-compaction 25 polls, fix récent) | [OBSERVÉ] |
| `accounts/` | poly-orchestrator | poly_strategy_account.py | POLY_TRADING_PUBLISHER (JS), Dashboard API | ❌ Non | [OBSERVÉ] |
| `trading/` | poly-orchestrator | poly_paper_execution_engine.py | POLY_TRADING_PUBLISHER (JS), Dashboard API, SYSTEM_WATCHDOG | ❌ Non (paper_trades_log.jsonl croissance) | [OBSERVÉ] |
| `feeds/` | poly-orchestrator | PolyBinanceFeed, PolyNoaaFeed, PolyWalletFeed | Dashboard API | ✅ Overwrite (dernier état) | [OBSERVÉ] |
| `registry/` | poly-orchestrator | poly_strategy_registry.py | POLY_TRADING_PUBLISHER (JS), Dashboard API | ❌ Non | [OBSERVÉ] |
| `orchestrator/` | poly-orchestrator | poly_heartbeat, orchestrator | SYSTEM_WATCHDOG, Dashboard API | ❌ Non | [OBSERVÉ] |
| `risk/` | poly-orchestrator | poly_kill_switch, poly_global_risk_guard | SYSTEM_WATCHDOG, Dashboard API | ❌ Non | [OBSERVÉ] |
| `llm/` | poly-orchestrator | poly_log_tokens.py | GLOBAL_TOKEN_TRACKER (JS), Dashboard API | ❌ Non (actuellement vide) | [OBSERVÉ] |
| `evaluation/` | poly-orchestrator | poly_strategy_evaluator | Dashboard API | ❌ Non | [OBSERVÉ] |
| `audit/` | poly-orchestrator | poly_audit_log | — | ❌ Non | [OBSERVÉ] |
| `human/` | poly-orchestrator | poly_strategy_promotion_gate | — | ❌ Non | [OBSERVÉ] |

---

## ~/openclaw/workspace/agents/

| Sous-dossier | Owner | Writers | Readers | Nettoyage auto ? | Tag |
|-------------|-------|---------|---------|-----------------|-----|
| `scraper/memory/` | Content scripts | hourly_scraper, scraper | Dashboard API | ❌ Non (cleanup.js dormant) | [OBSERVÉ] |
| `copywriter/memory/` | Content scripts | poller.js (modifications) | Dashboard API | ❌ Non | [OBSERVÉ] |
| `publisher/memory/` | Content scripts | twitter.js (publication logs) | Dashboard API | ❌ Non | [OBSERVÉ] |
| `builder/memory/` | Content scripts | — | Dashboard API | ❌ Non | [OBSERVÉ] |
| `analyst/reports/` | youtube_analyzer.js | youtube_analyzer (dormant) | — | ❌ Non | [OBSERVÉ] |

**Risque** : cleanup.js existe mais n'est pas schedulé → mémoire agents croît sans limite. [OBSERVÉ]

---

## ~/openclaw/workspace/skills_custom/

| Sous-dossier | Owner | Writers | Readers | Nettoyage auto ? | Tag |
|-------------|-------|---------|---------|-----------------|-----|
| `trading/` | Trading poller | Agents JS (handler.js) | — | ❌ Non (code, pas de state) | [OBSERVÉ] |
| `trading/SYSTEM_WATCHDOG/` | Cron watchdog | SYSTEM_WATCHDOG handler.js | — | ❌ Non | [OBSERVÉ] |
| `trading/POLY_TRADING_PUBLISHER/` | Trading poller | POLY_TRADING_PUBLISHER handler.js | — | ❌ Non | [OBSERVÉ] |
| `trading/GLOBAL_TOKEN_TRACKER/` | Trading poller | GLOBAL_TOKEN_TRACKER handler.js | — | ❌ Non | [OBSERVÉ] |
| `*.js` (racine) | Cron + Docker | hourly_scraper, scraper, poller, drafts, pending, twitter | — | ❌ Non (code) | [OBSERVÉ] |

---

## ~/openclaw/workspace/dashboard/

| Sous-dossier | Owner | Writers | Readers | Nettoyage auto ? | Tag |
|-------------|-------|---------|---------|-----------------|-----|
| `api/` | PM2 (dashboard-api) | Express server (cache en mémoire) | Client React | N/A (pas de state persistant) | [OBSERVÉ] |
| `api/.env` | openclawadmin | Manuel | dashboard-api | N/A | [OBSERVÉ] |
| `web/dist/` | Build Vite | `npm run build` | nginx (static) | N/A | [OBSERVÉ] |

---

## Dossiers sans owner clair

| Dossier | Problème | Tag |
|---------|----------|-----|
| `workspace/intel/` | Écrit par scraper.js, lu par personne d'identifié | [OBSERVÉ] |
| `workspace/state/` (racine, hors trading/) | Contient drafts.json, logs, etc. — partagé entre Content et scripts divers | [OBSERVÉ] |
| `workspace/recipes/` | Scripts automatisés, owner inconnu | [INCONNU] |

---

## Synthèse nettoyage

| Catégorie | Fichiers avec nettoyage | Fichiers sans nettoyage | Risque |
|-----------|------------------------|------------------------|--------|
| Bus Trading | ✅ rotation + cleanup | — | OK |
| Bus POLY | ✅ compaction (fix récent) | processed_events.jsonl (croissance) | MOYEN |
| Logs | ✅ poller.log (fix récent) | hourly_scraper.log, PM2 logs | FAIBLE |
| State Trading | — | token_costs.jsonl, trading_intel (72 Mo) | ÉLEVÉ |
| State POLY | — | paper_trades_log.jsonl, audit/ | MOYEN |
| Agents Content | — | Toute la mémoire (cleanup.js dormant) | MOYEN |
