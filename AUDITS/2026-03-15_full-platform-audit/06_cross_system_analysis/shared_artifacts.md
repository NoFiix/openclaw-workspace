# shared_artifacts.md — Inventaire des artefacts partagés

**Date** : 2026-03-15
**Scope** : Fichiers, variables, scripts et topics partagés entre systèmes

---

## Résumé exécutif

L'environnement OpenClaw a une séparation relativement propre entre systèmes. Les artefacts véritablement partagés sont peu nombreux : **2 fichiers JSONL** lus en cross-system, **1 clé API partagée** (Anthropic), **1 canal Telegram commun**, et **1 container Docker** hébergeant 2 systèmes. Le risque de multi-écriture est quasi nul — les dépendances sont en lecture seule. [OBSERVÉ]

---

## Fichiers state partagés

| Fichier/Dossier | Owner principal | Writers | Readers | Risque multi-écriture | Criticité | Tag |
|----------------|----------------|---------|---------|----------------------|-----------|-----|
| `POLY_FACTORY/state/accounts/*.json` | poly-orchestrator | poly-orchestrator (Python) | POLY_TRADING_PUBLISHER (JS), Dashboard API | Aucun (1 writer) | MOYEN | [OBSERVÉ] |
| `POLY_FACTORY/state/trading/paper_trades_log.jsonl` | poly-orchestrator | poly_paper_execution_engine (Python) | POLY_TRADING_PUBLISHER (JS), Dashboard API, SYSTEM_WATCHDOG | Aucun (1 writer, append-only) | MOYEN | [OBSERVÉ] |
| `POLY_FACTORY/state/registry/strategy_registry.json` | poly-orchestrator | poly_strategy_registry (Python) | POLY_TRADING_PUBLISHER (JS), Dashboard API | Aucun (1 writer) | FAIBLE | [OBSERVÉ] |
| `POLY_FACTORY/state/llm/token_costs.jsonl` | poly-orchestrator | poly_log_tokens.py (Python) | GLOBAL_TOKEN_TRACKER (JS), Dashboard API | Aucun (1 writer, append-only) | FAIBLE | [OBSERVÉ] |
| `POLY_FACTORY/state/orchestrator/heartbeat_state.json` | poly-orchestrator | poly_heartbeat (Python) | SYSTEM_WATCHDOG (JS), Dashboard API | Aucun (1 writer) | FAIBLE | [OBSERVÉ] |
| `POLY_FACTORY/state/risk/global_risk_state.json` | poly-orchestrator | poly_global_risk_guard (Python) | SYSTEM_WATCHDOG (JS), Dashboard API | Aucun (1 writer) | FAIBLE | [OBSERVÉ] |
| `state/learning/token_costs.jsonl` | Trading poller | logTokens.js (JS agents) | GLOBAL_TOKEN_TRACKER (JS), Dashboard API | Aucun (1 writer, append-only) | FAIBLE | [OBSERVÉ] |
| `state/learning/token_summary.json` | GLOBAL_TOKEN_TRACKER | GLOBAL_TOKEN_TRACKER (JS) | GLOBAL_TOKEN_ANALYST (JS), Dashboard API | Aucun (1 writer, overwrite) | FAIBLE | [OBSERVÉ] |
| `state/trading/exec/killswitch.json` | Trading poller | KILL_SWITCH_GUARDIAN (JS) | SYSTEM_WATCHDOG (JS), Dashboard API | Aucun (1 writer) | MOYEN | [OBSERVÉ] |
| `state/drafts.json` | Content poller | hourly_scraper (JS), poller (JS) | Dashboard API | **2 writers** possibles | MOYEN | [OBSERVÉ] |
| `state/watchdog_heartbeat` | Watchdog cron | run_watchdog.sh (Bash) | check_watchdog_heartbeat.sh (Bash) | Aucun (1 writer) | FAIBLE | [OBSERVÉ] |

### Fichier avec risque multi-écriture

`state/drafts.json` est écrit par `hourly_scraper.js` (cron horaire) ET `poller.js` (daemon continu). Risque théorique de corruption si les deux écrivent simultanément. En pratique, hourly_scraper écrit une seule fois par heure et poller modifie des drafts existants → collision improbable mais non protégée (pas de lock). [DÉDUIT]

---

## Variables d'environnement partagées

### Clés API potentiellement identiques

| Variable | Systèmes | Fichier(s) .env | Même valeur ? | Risque | Tag |
|----------|----------|----------------|---------------|--------|-----|
| `ANTHROPIC_API_KEY` | Content + Trading + POLY | Container .env, POLY_FACTORY/.env | Probablement oui | Révocation = 3 systèmes down | [DÉDUIT] |
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | Trading + POLY | Container .env, POLY_FACTORY/.env | Possiblement même clé | Rate limiting partagé | [DÉDUIT] |
| `TELEGRAM_BOT_TOKEN` | Watchdog | Container .env | Distinct des autres bots | — | [OBSERVÉ] |
| `BUILDER_TELEGRAM_BOT_TOKEN` | Content | Container .env | Distinct | — | [OBSERVÉ] |
| `TRADER_TELEGRAM_BOT_TOKEN` | Trading | Container .env | Distinct | — | [OBSERVÉ] |
| `POLY_TELEGRAM_BOT_TOKEN` | POLY | POLY_FACTORY/.env | Distinct | — | [OBSERVÉ] |

### Chat IDs Telegram — tous identiques

| Variable | Valeur | Systèmes | Tag |
|----------|--------|----------|-----|
| `TELEGRAM_CHAT_ID` | 1066147184 | Watchdog | [OBSERVÉ] |
| `BUILDER_TELEGRAM_CHAT_ID` | 1066147184 | Content | [OBSERVÉ] |
| `TRADER_TELEGRAM_CHAT_ID` | 1066147184 | Trading | [OBSERVÉ] |
| `POLY_TELEGRAM_CHAT_ID` | 1066147184 | POLY | [OBSERVÉ] |

**Conclusion** : 4 bots différents, 1 seul canal. 14 émetteurs dans le même chat. [OBSERVÉ]

---

## Scripts et modules partagés

| Script/Module | Localisation | Utilisé par | Rôle | Cross-system ? | Tag |
|--------------|-------------|------------|------|---------------|-----|
| `logTokens.js` | `skills_custom/trading/_shared/` | 24 agents Trading JS | Log coûts LLM → token_costs.jsonl | Non (Trading only) | [OBSERVÉ] |
| `poly_log_tokens.py` | `POLY_FACTORY/core/` | Agents POLY Python | Log coûts LLM → token_costs.jsonl (POLY) | Non (POLY only) | [OBSERVÉ] |
| `drafts.js` | `skills_custom/` | hourly_scraper, poller | Gestion drafts Content | Non (Content only) | [OBSERVÉ] |
| `pending.js` | `skills_custom/` | scraper, poller | Sélection articles Content | Non (Content only) | [OBSERVÉ] |
| `twitter.js` | `skills_custom/` | poller | Publication Twitter | Non (Content only) | [OBSERVÉ] |
| `busRead.js` / `busWrite.js` | `skills_custom/trading/_shared/` | Agents Trading JS | Bus JSONL Trading | Non (Trading only) | [DÉDUIT] |
| `poly_event_bus.py` | `POLY_FACTORY/core/` | Agents POLY Python | Bus JSONL POLY | Non (POLY only) | [OBSERVÉ] |

**Aucun module n'est véritablement cross-system.** Chaque système a ses propres modules. Les lectures croisées passent par les fichiers state (JSONL, JSON). [OBSERVÉ]

---

## Topics bus — comparaison JS vs Python

### Bus Trading (JS) — `state/trading/bus/`

| Topic | Producteur | Consommateur | Tag |
|-------|-----------|-------------|-----|
| `trading.prices.*` | BINANCE_PRICE_FEED | Tous les agents signal | [OBSERVÉ] |
| `trading.signals.*` | TRADE_GENERATOR, SIGNAL_GENERATOR | TRADING_ORCHESTRATOR | [OBSERVÉ] |
| `trading.exec.*` | TRADING_ORCHESTRATOR | PAPER_EXECUTOR, TESTNET_EXECUTOR | [OBSERVÉ] |
| `trading.risk.*` | RISK_MANAGER | KILL_SWITCH_GUARDIAN | [OBSERVÉ] |
| `trading.ops.*` | Divers | TRADING_PUBLISHER, SYSTEM_WATCHDOG | [DÉDUIT] |
| `trading.intel.*` | NEWS_FEED, WHALE_FEED | NEWS_SCORING, MARKET_EYE | [OBSERVÉ] |

### Bus POLY (Python) — `POLY_FACTORY/state/bus/`

| Topic | Producteur | Consommateur | Tag |
|-------|-----------|-------------|-----|
| `feed:binance_update` | PolyBinanceFeed | Stratégies, MSA | [OBSERVÉ] |
| `feed:price_update` | PolyBinanceFeed | Stratégies | [OBSERVÉ] |
| `trade:signal` | Stratégies (5 actives) | PolyExecutionRouter | [OBSERVÉ] |
| `execute:paper` | PolyExecutionRouter | PolyPaperExecutionEngine | [OBSERVÉ] |
| `trade:paper_executed` | PolyPaperExecutionEngine | PolyStrategyEvaluator | [OBSERVÉ] |
| `system:heartbeat` | PolyHeartbeat | PolySystemMonitor | [OBSERVÉ] |
| `risk:kill_switch` | PolyKillSwitch | Tous les agents | [OBSERVÉ] |
| `news:high_impact` | **AUCUN** (bridge manquant C-12) | PolyNewsStrat | [OBSERVÉ] |

### Risques de collision de topics

| Risque | Détail | Tag |
|--------|--------|-----|
| Noms similaires | `trading.prices.*` (JS) vs `feed:price_update` (Python) — noms différents, OK | [OBSERVÉ] |
| Fichiers séparés | Bus JS dans `state/trading/bus/`, Bus Python dans `POLY_FACTORY/state/bus/` — aucun risque de collision | [OBSERVÉ] |
| Bridge manquant | `news:high_impact` devrait être alimenté par NEWS_SCORING (JS) mais aucun pont n'existe | [OBSERVÉ] |

**Conclusion** : Les deux bus sont **physiquement et logiquement séparés**. Aucun topic identique. Aucun risque de collision. Le seul manque est le bridge `news:high_impact` (C-12). [OBSERVÉ]
