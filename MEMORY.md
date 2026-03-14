# MEMORY.md - Mémoire long terme d'OpenClaw

## Dernière mise à jour
2026-03-14

---

## Session 2026-03-14 — POLY_FACTORY : déploiement + intégrations + corrections

### 1. Déploiement initial POLY_FACTORY sur VPS
- Python 3.11 installé sur VPS (venv dédié)
- `py-clob-client` installé dans le venv
- Clés Polymarket générées via `py-clob-client` ; clés Binance mainnet ajoutées
- `.env` complet et sécurisé (jamais commité)
- `run_orchestrator.py` créé par Claude Code
- `PM2 ecosystem.config.cjs` configuré — `poly-orchestrator` online en paper mode (0 restarts)
- `trading-poller` également ajouté sous PM2 avec autorestart (était mort silencieusement)
- **4 processus PM2 online** : dashboard-api, poly-orchestrator, trading-poller (+ watcher)

### 2. Intégrations OpenClaw
- **SYSTEM_WATCHDOG** étendu : surveille `poly-orchestrator` + kill switch global POLY + section dans rapport 08h
- `bus.compact()` appelé dans `run_nightly()` pour éviter la croissance infinie du fichier bus
- **POLY_TRADING_PUBLISHER** créé : 15 messages Telegram (paper/live trades, daily 20h Paris, weekly dimanche)
  - Nouveau bot Telegram dédié POLY_FACTORY (`POLY_TELEGRAM_BOT_TOKEN` + `POLY_TELEGRAM_CHAT_ID`)
- **`poly_log_tokens.py`** : tracking coûts LLM Python → `state/llm/token_costs.jsonl` (3 composants LLM patchés pour capturer `response.usage`)
- **`logTokens.js`** : prix `claude-sonnet-4-6` et `claude-opus-4-6` ajoutés
- **GLOBAL_TOKEN_TRACKER** : lit maintenant `POLY_FACTORY/state/llm/token_costs.jsonl`
- **`health.js`** : surveillance `poly-orchestrator` + `system_state.json` POLY ajoutés
- **`Overview.jsx`** : bannière kill switch POLY + 4 MetricCards POLY
- **`SystemMap.jsx`** : groupe Polymarket 29 composants, filtre, `CONTEXT_BUNDLE_POLYMARKET`

### 3. Dashboard Polymarket
- Backend Express : 4 endpoints — `/polymarket/live` `/polymarket/strategies` `/polymarket/trades` `/polymarket/health`
  - Cache TTL : 30s (live/health), 60s (strategies/trades)
  - Lit depuis `POLY_BASE_PATH` (env var, fallback hardcodé)
- Frontend React : page complète (KPI strip, equity charts, 9 strategy cards, leaderboard, trade feed, risk panel, promotion gate, agent health)
- Spec UI rédigée par le père de Dan — niveau desk quant professionnel

### 4. Bugs critiques corrigés (audit audit_global.md)

| Priorité | Bug | Corrigé dans |
|---|---|---|
| P0 | `expected_fill_price` manquant → chaîne paper trading cassée | `poly_factory_orchestrator.py` + `poly_execution_router.py` |
| P0 | SYSTEM_WATCHDOG lisait `portfolio_state.json` au lieu de `global_risk_state.json` | `SYSTEM_WATCHDOG/handler.js` (2 occurrences) |
| P0 | Poller trading hors PM2 → mort silencieux sans supervision | `ecosystem.config.cjs` créé |
| P1 | 48 tests en échec (mocks LLM sans `.usage`, `TEST_DATE` périmé) | `test_opp_scorer.py`, `test_no_scanner.py`, `test_compounder.py` |
| P1 | `daily_pnl_eur` vs `pnl.daily` → P&L toujours 0 en dashboard | `polymarket.js` (2 locations) + `POLY_TRADING_PUBLISHER/handler.js` |
| P2 | `_acked_ids` non borné → fuite mémoire bus | `poly_event_bus.py` → `deque(maxlen=10000)` |
| P2 | `PolyDataStore.SUBDIRS` incomplets | `poly_data_store.py` → `llm/`, `orchestrator/`, `memory/`, `strategies/` ajoutés |
| P2 | `PolyDecayDetector` sans producteur → starved | `poly_paper_execution_engine.py` écrit `{strategy}_pnl.jsonl` à chaque trade |
| P2 | `connector_polymarket.py` non fonctionnel | `get_positions()` + `place_order()` implémentés via `py_clob_client` |
| P2 | `POLY_BASE_PATH` hardcodé dans `polymarket.js` | `process.env.POLY_BASE_PATH` avec fallback |
| P3 | Bus sans compaction automatique | `compact()` toutes les 100 itérations de `poll()` si >10 000 événements |
| P3 | 6 agents non-critiques plantaient le poller | `critical: false` dans 6 schedules + try/catch dans `poller.js` |

### 5. Architecture ajoutée
- **20 JSON schemas draft-07** dans `POLY_FACTORY/schemas/` (un par topic bus : trade:signal, execute:paper/live, feed:price_update/noaa/wallet, signal:binance/market_structure/wallet_convergence/resolution_parsed, data:validation_failed, system:health_check/agent_stale/disabled, risk:kill_switch/global_status, trade:paper/live opened/closed)
- **`validate_payload(topic, payload)`** dans `poly_event_bus.py` — warn-only (non bloquant), jsonschema v3.2.0

### 6. État système au 2026-03-14
- **Tests** : 1285 passent, 0 failure
- **PM2** : poly-orchestrator online (paper mode, 0 restarts), trading-poller online, dashboard-api online
- **Paper trading** : actif — 0 trades pour l'instant (phase d'initialisation)
- **Telegram** : daily report 20h Paris configuré via POLY_TRADING_PUBLISHER
- **Fichiers audit** : `~/openclaw/workspace/audit_global.md`, `fixes_done.md`, `fixes_done_2.md`, `fixes_done_3.md`

---

## Modèles IA disponibles
### OpenAI (OPENAI_API_KEY)
- openai/gpt-4o-mini → tâches légères, résumés, classification
- openai/gpt-4o → tâches intermédiaires

### Anthropic (ANTHROPIC_API_KEY)
- anthropic/claude-haiku-4-5 → notifications, tri emails, résumés rapides, support client
- anthropic/claude-sonnet-4-5 → rédaction, analyse, storytelling
- anthropic/claude-opus-4-6 → code, tâches critiques, auto-amélioration

## Règle de routing
Score = Importance (1-5) + Sensibilité (1-5) + Complexité (1-5)
- 3-4 → claude-haiku-4-5
- 5-6 → gpt-4o-mini
- 7-8 → gpt-4o
- 9-11 → claude-sonnet-4-5
- 12-15 → claude-opus-4-6

## Recipes actives
- daily_crypto_recap : tous les jours à 19h Europe/Paris
  Pipeline : digest numéroté → Daniel choisit → post Twitter réécrit → validation → publication

## Ce que Daniel attend de moi
- Réponses courtes, directes, sans remplissage
- Toujours proposer des améliorations proactivement
- Jamais agir sur l'externe sans validation Telegram
- Jamais modifier le core OpenClaw
- Logger toutes les actions importantes dans workspace/state/

## Leçons apprises
_(à remplir au fil du temps)_

## Projets en cours
- Configuration OpenClaw complète (infrastructure IA personnelle)
- Pipeline Twitter CryptoRizon automatisé
- Tri emails tutorizonofficiel@gmail.com + khuddan@gmail.com
