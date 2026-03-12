# POLY_FACTORY — Backlog de Développement

> **Version 2.0 — 12 mars 2026**
> Backlog orienté exécution réelle pour construire POLY_FACTORY dans OpenClaw / Claude Code.
> Basé sur ARCHITECTURE v4.0, PIPELINE v4.0, IMPLEMENTATION_PLAN v3.0.

---

## AMÉLIORATIONS v2

| # | Amélioration | Impact |
|---|---|---|
| 1 | **Estimation fine par ticket** — Chaque ticket a une taille (S/M/L/XL), une difficulté (low/med/high), et un risque de blocage avec explication. | Tous les tickets |
| 2 | **Type et statut** — Chaque ticket porte un `type` (infra/data/signal/strategy/risk/execution/evaluation/test) et un `status` (todo/ready/blocked/done). | Tous les tickets |
| 3 | **Artifacts systématiques** — Chaque ticket liste explicitement les fichiers Python, state, config et tests à créer. | Tous les tickets |

**Légende taille** : S = < 1 jour, M = 1-2 jours, L = 2-4 jours, XL = 4+ jours.
**Légende difficulté** : LOW = logique simple, MED = logique complexe ou intégration multi-agents, HIGH = API externe fragile ou sécurité critique.
**Légende risque** : LOW = pas de blocage probable, MED = dépendance externe ou complexité cachée, HIGH = API instable ou module safety-critical.

---

## 1. RÈGLES GÉNÉRALES DE DÉVELOPPEMENT

**Conventions** : préfixe `POLY_`. Fichiers : `poly_{agent}.py`. State : `state/{cat}/{file}.json`. Bus : `{cat}:{action}`.

**Séparation paper/live** : deux modules distincts. Paper n'importe JAMAIS py-clob-client. Router basé sur Registry.

**Bus** : JSON Lines `state/bus/pending_events.jsonl`. Polling 1-5s. Enveloppe : `{event_id, topic, timestamp, producer, priority, retry_count, payload}`.

**Idempotence** : set 10 000 derniers event_ids par consommateur.

**Sécurité** : défaut = paper. Live = Promotion Gate 10 checks + humain + flag `--live`. Global Risk Guard coupe à 4 000€.

**Environnement** : VPS Hostinger, Python 3.11+, PM2, Node.js poller, ctx.state, Git.

---

## 2. VUE D'ENSEMBLE DU BACKLOG

| Phase | Objectif | Livrable | Tickets |
|---|---|---|---|
| **1 — Data** | Données affluent | Feeds 24h, bus, audit | POLY-001 à 007 |
| **2 — Signaux** | Données validées et enrichies | Signaux exploitables | POLY-008 à 012 |
| **3 — Backtest** | Tri rapide des idées | Backtest en minutes | POLY-013 |
| **4 — Paper** | Stratégies en fictif | 2 stratégies 1 000€ paper | POLY-014 à 020 |
| **5 — Risque** | Protection + évaluation | Kill switch, evaluator | POLY-021 à 027 |
| **6 — Stratégies** | Portefeuille complet | 9 stratégies paper | POLY-028 à 034 |
| **7 — Live** | Pipeline complet | Micro-live possible | POLY-035 à 041 |
| **8 — Monitoring** | Surveillance | Alertes, robustesse | POLY-042 à 043 |
| **9 — Multi** | Cross-plateforme | Connecteur Kalshi | POLY-044 à 045 |
| **Tests** | Validation | Couverture complète | POLY-T01 à T07 |

---

## 3. BACKLOG DÉTAILLÉ PAR PHASE

---

### PHASE 1 — DATA FOUNDATIONS

---

#### POLY-001 — Create POLY_DATA_STORE base structure

| | |
|---|---|
| Type | `infra` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **LOW** — création de fichiers et méthodes CRUD |
| Risque | **LOW** — pas de dépendance externe |
| Priorité | P0 |

**Objectif** : couche de persistance centrale avec arborescence state/ complète.

**Dépendances** : aucune (premier ticket)

**Étapes** :
1. Créer l'arborescence state/ : orchestrator/, accounts/, risk/, feeds/, trading/, evaluation/, research/, human/, audit/, bus/, registry/, historical/
2. Implémenter read/write via ctx.state OpenClaw
3. Implémenter archivage (accounts archive/)
4. Créer les fichiers JSON initiaux vides
5. Implémenter SQLite init (historical/markets.db, signals.db)

**Critères d'acceptation** :
- Toutes les sous-arborescences existent sur le VPS
- read/write ctx.state fonctionnel
- Fichiers JSON valides et parsables

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_data_store.py` |
| State | `state/` (12 sous-dossiers), tous les fichiers JSON initiaux |
| Config | `AGENT.md`, `SOUL.md`, `MEMORY.md` |
| Test | `tests/test_data_store.py` — read/write round-trip, JSON Lines integrity, 1000 lignes sans corruption |

---

#### POLY-002 — Create POLY_AUDIT_LOG

| | |
|---|---|
| Type | `infra` |
| Status | `todo` |
| Taille | **S** (0.5-1 jour) |
| Difficulté | **LOW** — append JSON Lines |
| Risque | **LOW** — pas de dépendance externe |
| Priorité | P0 |

**Objectif** : journalisation transversale immuable (append-only JSON Lines).

**Dépendances** : POLY-001

**Étapes** :
1. Implémenter `log_event(topic, producer, payload, priority)`
2. Générer event_id unique : `EVT_{date}_{time}_{counter}`
3. Formater enveloppe commune
4. Écrire append-only dans `audit_YYYY_MM_DD.jsonl`
5. Rotation quotidienne + archivage hebdomadaire (> 90j)

**Critères d'acceptation** :
- Append-only vérifié (fichier jamais réécrit)
- event_id uniques même sous charge
- Rotation à minuit crée nouveau fichier

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_audit_log.py` |
| State | `state/audit/audit_YYYY_MM_DD.jsonl`, `state/audit/archive/` |
| Test | `tests/test_audit_log.py` — 100 events rapides → tous présents et uniques, crash mid-write → fichier parsable |

---

#### POLY-003 — Create Event Bus

| | |
|---|---|
| Type | `infra` |
| Status | `todo` |
| Taille | **L** (2-3 jours) |
| Difficulté | **MED** — modes écrasement/queue/cache/sync/prioritaire |
| Risque | **MED** — c'est le backbone du système, les bugs ici se propagent partout |
| Priorité | P0 |

**Objectif** : bus de communication via fichier JSON Lines + polling avec idempotence.

**Dépendances** : POLY-001, POLY-002

**Étapes** :
1. Implémenter `publish(topic, producer, payload, priority)`
2. Implémenter `poll(consumer_id)` avec filtrage par topic
3. Implémenter `ack(consumer_id, event_id)`
4. Implémenter set d'idempotence (10 000 derniers IDs)
5. Implémenter retry (retry_count + 1, dead_letter après 3)
6. Implémenter mode prioritaire (high avant normal)
7. Implémenter mode écrasement (dernière valeur par clé)

**Critères d'acceptation** :
- Event publié → lisible par poll() en < 5s
- Event ack'd → plus retourné
- Même event_id 2x → consommé 1x
- 3 échecs → dead_letter.jsonl
- High priority traité en premier

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_event_bus.py` |
| State | `state/bus/pending_events.jsonl`, `state/bus/processed_events.jsonl`, `state/bus/dead_letter.jsonl` |
| Test | `tests/test_event_bus.py` — publish/poll/ack cycle, idempotence, dead letter, priority ordering, écrasement mode |

---

#### POLY-004 — Create POLY_MARKET_CONNECTOR (connector_polymarket)

| | |
|---|---|
| Type | `data` |
| Status | `todo` |
| Taille | **L** (2-3 jours) |
| Difficulté | **HIGH** — WebSocket Polymarket instable, reconnexion, rate limits |
| Risque | **HIGH** — API Polymarket peut changer sans préavis, WebSocket drops fréquents |
| Priorité | P0 |

**Objectif** : abstraction multi-plateformes + premier connecteur Polymarket.

**Dépendances** : POLY-001, POLY-003

**Étapes** :
1. Définir interface ABC : get_markets(), get_orderbook(), place_order(), get_positions(), get_settlement()
2. Implémenter connector_polymarket : WebSocket CLOB + Gamma API REST
3. WebSocket persistent avec reconnexion auto (backoff exponentiel)
4. Écrire prix dans state/feeds/polymarket_prices.json avec champ `platform`
5. Publier `feed:price_update` sur le bus
6. Health check ping 60s
7. Config JSON connecteurs actifs

**Critères d'acceptation** :
- WebSocket connecté 24h sans interruption
- Prix YES/NO mis à jour dans le fichier state
- Reconnexion auto après déconnexion simulée en < 30s

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_market_connector.py` (interface ABC), `connectors/connector_polymarket.py` |
| State | `state/feeds/polymarket_prices.json` |
| Config | `connectors/POLY_MARKET_CONNECTOR.config.json` |
| Env | `.env` : POLYMARKET_API_KEY, POLYMARKET_API_SECRET |
| Test | `tests/test_market_connector.py` — connexion, reconnexion, format payload feed:price_update |

---

#### POLY-005 — Create POLY_BINANCE_FEED

| | |
|---|---|
| Type | `data` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — WebSocket stable mais parsing aggTrade + depth |
| Risque | **MED** — Binance peut déconnecter si rate limit dépassé |
| Priorité | P0 |

**Objectif** : flux WebSocket Binance pour prix BTC/ETH + orderbook depth20.

**Dépendances** : POLY-001, POLY-003

**Étapes** :
1. Connexion WebSocket Binance (aggTrade + depth20@100ms)
2. Parser ticks → state/feeds/binance_raw.json
3. Publier `feed:binance_update` sur le bus
4. Reconnexion auto, gestion rate limits

**Critères d'acceptation** :
- Prix arrivent en continu, latence < 200ms
- Reconnexion auto après déconnexion

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_binance_feed.py` |
| State | `state/feeds/binance_raw.json` |
| Env | `.env` : BINANCE_API_KEY |
| Test | `tests/test_binance_feed.py` — latence, format payload, reconnexion |

---

#### POLY-006 — Create POLY_NOAA_FEED

| | |
|---|---|
| Type | `data` |
| Status | `todo` |
| Taille | **S** (0.5-1 jour) |
| Difficulté | **LOW** — REST simple, sans auth |
| Risque | **MED** — NWS retourne des 503 aléatoires, format varie par station |
| Priorité | P1 |

**Objectif** : fetch prévisions NWS pour 6 stations aéroport US toutes les 2 min.

**Dépendances** : POLY-001, POLY-003

**Étapes** :
1. Mapping 6 stations (KLGA, KORD, KMIA, KDAL, KSEA, KATL)
2. Fetch api.weather.gov toutes les 2 min
3. Combiner observations + forecast → daily max par ville
4. Écrire state + publier `feed:noaa_update`
5. Gestion erreurs HTTP (retry si 503)

**Critères d'acceptation** :
- 6 villes avec prévisions < 5 min de fraîcheur
- Pas de crash si NWS retourne 503

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_noaa_feed.py` |
| State | `state/feeds/noaa_forecasts.json` |
| Config | `references/station_mapping.json` |
| Test | `tests/test_noaa_feed.py` — 6 stations présentes, gestion erreur 503 |

---

#### POLY-007 — Create POLY_WALLET_FEED

| | |
|---|---|
| Type | `data` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — parsing positions on-chain via Polygon RPC |
| Risque | **MED** — QuickNode free tier peut rate-limit |
| Priorité | P1 |

**Objectif** : fetch positions brutes wallets Polymarket toutes les 60s.

**Dépendances** : POLY-001, POLY-003

**Étapes** :
1. Liste initiale 10-20 wallets
2. Fetch via Polymarket API + Polygon RPC
3. Écrire state + publier `feed:wallet_update`

**Critères d'acceptation** :
- Positions mises à jour toutes les 60s
- Détection < 2 min après transaction on-chain

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_wallet_feed.py` |
| State | `state/feeds/wallet_raw_positions.json` |
| Config | `references/tracked_wallets.json` |
| Env | `.env` : POLYGON_RPC_URL |
| Test | `tests/test_wallet_feed.py` — positions cohérentes, format payload |

---

### PHASE 2 — SIGNAL LAYER

---

#### POLY-008 — Create POLY_DATA_VALIDATOR

| | |
|---|---|
| Type | `data` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — nombreuses règles de validation par source |
| Risque | **LOW** — logique déterministe, pas de dépendance externe |
| Priorité | P0 |

**Objectif** : filtrer les données corrompues avant qu'elles n'atteignent les stratégies.

**Dépendances** : POLY-004, POLY-005, POLY-006, POLY-007

**Étapes** :
1. Règles prix : [0.01, 0.99], YES+NO dans [0.95, 1.05], variation < 30%, timestamp < 30s, pas de doublons
2. Règles Binance : OBI [-1,+1], prix variation < 5%, pas de gap > 5s
3. Règles NOAA : température [-50°F, +140°F], forecast < 6h, 6 stations
4. Règles wallets : positions ≥ 0, pas de spam
5. Marquer SUSPECT dans le fichier state
6. Publier `data:validation_failed` si anomalie

**Critères d'acceptation** :
- Prix 0.00 → SUSPECT. Timestamp -5min → SUSPECT. Données valides → VALID.

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_data_validator.py` |
| Config | `references/validation_rules.json` (seuils configurables) |
| Test | `tests/test_data_validator.py` — injection prix 0, timestamp stale, données valides, 5 échecs consécutifs → alerte |

---

#### POLY-009 — Create POLY_BINANCE_SIGNALS

| | |
|---|---|
| Type | `signal` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — calculs OBI/CVD/VWAP/Momentum en < 100ms |
| Risque | **LOW** — logique mathématique pure, pas de dépendance externe |
| Priorité | P1 |

**Objectif** : transformer données brutes Binance en OBI, CVD, VWAP, Momentum, score [-1,+1].

**Dépendances** : POLY-005, POLY-008

**Étapes** :
1. Calculer OBI depuis orderbook depth20
2. Calculer CVD depuis aggTrade
3. Calculer VWAP Position
4. Calculer Momentum (EMA 5/20 cross)
5. Score composite [-1,+1] = moyenne pondérée
6. Écrire state + publier `signal:binance_score`

**Critères d'acceptation** :
- Score calculé en < 50ms après tick. OBI et score dans [-1,+1].

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_binance_signals.py` |
| State | `state/feeds/binance_signals.json` |
| Test | `tests/test_binance_signals.py` — OBI sur orderbook connu, latence < 100ms |

---

#### POLY-010 — Create POLY_MARKET_STRUCTURE_ANALYZER

| | |
|---|---|
| Type | `signal` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — modèle de slippage réaliste |
| Risque | **LOW** — logique déterministe |
| Priorité | P0 |

**Objectif** : microstructure par marché (liquidité, spread, profondeur, slippage, score 0-100).

**Dépendances** : POLY-004, POLY-008

**Étapes** :
1. liquidity_score, spread_bps, depth_usd, slippage_1k
2. executability_score composite 0-100
3. Écrire toutes les 30s + publier `market:illiquid` si score chute

**Critères d'acceptation** :
- Marché $50 liquidité → score < 40. Marché $5K, spread 1% → score > 70.

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_market_structure_analyzer.py` |
| State | `state/feeds/market_structure.json` |
| Test | `tests/test_market_structure.py` — score sur orderbooks synthétiques |

---

#### POLY-011 — Create POLY_WALLET_TRACKER

| | |
|---|---|
| Type | `signal` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — EV scoring + convergence detection |
| Risque | **LOW** |
| Priorité | P1 |

**Objectif** : signaux enrichis wallets (EV, spécialisation, convergence).

**Dépendances** : POLY-007, POLY-008

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_wallet_tracker.py` |
| State | `state/feeds/wallet_signals.json` |
| Config | `references/wallet_blacklist_rules.json` |
| Test | `tests/test_wallet_tracker.py` — 3 wallets convergent → event émis, spam wallet → blacklisté |

---

#### POLY-012 — Create POLY_MARKET_ANALYST

| | |
|---|---|
| Type | `signal` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — prompt engineering Sonnet + cache |
| Risque | **MED** — qualité du parsing dépend du prompt, coût LLM si cache raté |
| Priorité | P1 |

**Objectif** : parser critères de résolution via Sonnet (1 appel/marché, résultat caché).

**Dépendances** : POLY-004, POLY-002

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_market_analyst.py` |
| State | `state/research/resolutions_cache.json` |
| Config | `prompts/resolution_parser_prompt.txt` |
| Test | `tests/test_market_analyst.py` — parsing 5 marchés connus, cache hit (pas de 2e appel LLM) |

---

### PHASE 3 — BACKTEST

---

#### POLY-013 — Create POLY_BACKTEST_ENGINE

| | |
|---|---|
| Type | `evaluation` |
| Status | `todo` |
| Taille | **L** (2-3 jours) |
| Difficulté | **MED** — replay historique, métriques financières |
| Risque | **MED** — qualité du backtest dépend de la quantité de données historiques accumulées (Phase 1 doit tourner assez longtemps) |
| Priorité | P1 |

**Objectif** : replay marchés historiques — outil de TRI rapide, PAS de validation.

**Dépendances** : POLY-001, POLY-008

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_backtest_engine.py` |
| State | `state/research/backtest_results/` |
| Test | `tests/test_backtest_engine.py` — backtest dataset synthétique → métriques vérifiées, max 3 simultanés |

---

### PHASE 4 — PAPER TRADING

---

#### POLY-014 — Create POLY_STRATEGY_REGISTRY

| | |
|---|---|
| Type | `infra` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **LOW** — CRUD + versioning |
| Risque | **LOW** |
| Priorité | P0 |

**Objectif** : registre central de la vie logique des stratégies.

**Dépendances** : POLY-001

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_strategy_registry.py` |
| State | `state/registry/strategy_registry.json` |
| Test | `tests/test_strategy_registry.py` — register, update_status, update_parameters → historique complet, persistence après restart |

---

#### POLY-015 — Create POLY_STRATEGY_ACCOUNT model

| | |
|---|---|
| Type | `infra` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — calcul drawdown vs high_water_mark, archivage |
| Risque | **LOW** |
| Priorité | P0 |

**Objectif** : modèle de données comptes stratégie (capital isolé 1 000€).

**Dépendances** : POLY-001, POLY-014

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_strategy_account.py` |
| State | `state/accounts/ACC_POLY_{STRATEGY}.json`, `state/accounts/archive/` |
| Test | `tests/test_strategy_account.py` — create, trade +50€, trade -100€ → capital/pnl/drawdown vérifiés |

---

#### POLY-016 — Create POLY_KELLY_SIZER

| | |
|---|---|
| Type | `risk` |
| Status | `todo` |
| Taille | **S** (< 1 jour) |
| Difficulté | **LOW** — formule mathématique pure |
| Risque | **LOW** |
| Priorité | P1 |

**Objectif** : taille de position basée sur le capital du POLY_STRATEGY_ACCOUNT.

**Dépendances** : POLY-015

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_kelly_sizer.py` |
| Test | `tests/test_kelly_sizer.py` — calculs vérifiés, max 3% du compte |

---

#### POLY-017 — Create POLY_PAPER_EXECUTION_ENGINE

| | |
|---|---|
| Type | `execution` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — slippage réaliste basé sur market_structure |
| Risque | **HIGH** — module safety-critical : doit être physiquement incapable d'envoyer un ordre réel |
| Priorité | P0 |

**Objectif** : moteur d'exécution paper. AUCUNE dépendance py-clob-client.

**Dépendances** : POLY-003, POLY-010, POLY-015

**Étapes** :
1. Écouter `execute:paper` sur le bus
2. Prix ask/bid réel + slippage basé sur market_structure.slippage_1k
3. Fees estimés
4. Écrire trade dans paper_trades_log.jsonl
5. Appeler account.update_after_trade()
6. Publier `trade:paper_executed`
7. **VÉRIFIER : grep "py_clob_client\|py-clob-client" → 0 résultats**

**Critères d'acceptation** :
- AUCUN import py-clob-client (vérifié par grep)
- Slippage réaliste (pas forfaitaire)
- Account mis à jour après chaque trade

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_paper_execution_engine.py` |
| State | `state/trading/paper_trades_log.jsonl` |
| Test | `tests/test_paper_execution.py` — grep py-clob → 0, trade simulé → account MAJ, format log conforme |

---

#### POLY-018 — Create POLY_ORDER_SPLITTER

| | |
|---|---|
| Type | `execution` |
| Status | `todo` |
| Taille | **S** (< 1 jour) |
| Difficulté | **LOW** |
| Risque | **LOW** |
| Priorité | P1 |

**Objectif** : découper ordres en tranches calibrées par depth_usd.

**Dépendances** : POLY-010

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_order_splitter.py` |
| Test | `tests/test_order_splitter.py` — split avec différentes profondeurs |

---

#### POLY-019 — Create POLY_ARB_SCANNER (première stratégie)

| | |
|---|---|
| Type | `strategy` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — logique d'arb + intégration bus |
| Risque | **MED** — dépend de la qualité des prix Polymarket (POLY-004) |
| Priorité | P0 |

**Objectif** : stratégie arbitrage Bundle YES+NO + Dutch Book.

**Dépendances** : POLY-004, POLY-010, POLY-003, POLY-014, POLY-015

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `strategies/poly_arb_scanner.py` |
| State | via POLY_STRATEGY_ACCOUNT + POLY_STRATEGY_REGISTRY |
| Test | `tests/test_arb_scanner.py` — signal émis si sum < 0.97, pas de signal si sum ≥ 0.97, payload conforme |

---

#### POLY-020 — Create POLY_WEATHER_ARB

| | |
|---|---|
| Type | `strategy` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — mapping villes/buckets Polymarket |
| Risque | **MED** — dépend de la disponibilité de marchés weather sur Polymarket |
| Priorité | P1 |

**Objectif** : arbitrage weather NOAA vs Polymarket.

**Dépendances** : POLY-006, POLY-004, POLY-010, POLY-003

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `strategies/poly_weather_arb.py` |
| Config | `references/weather_market_mapping.json` |
| Test | `tests/test_weather_arb.py` — NOAA 82°F 90% + bucket 0.12 → signal, bucket 0.85 → pas de signal |

---

### PHASE 5 — RISK & EVALUATION

---

#### POLY-021 — Create POLY_KILL_SWITCH

| | |
|---|---|
| Type | `risk` |
| Status | `todo` |
| Taille | **L** (2-3 jours) |
| Difficulté | **HIGH** — 5 niveaux de réponse, tick 5s, pré-trade sync |
| Risque | **HIGH** — safety-critical, erreur = perte de capital |
| Priorité | P0 |

**Objectif** : protection par stratégie/session. Override total. 5 niveaux.

**Dépendances** : POLY-015, POLY-003, POLY-002

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_kill_switch.py` |
| State | `state/risk/kill_switch_status.json` |
| Test | `tests/test_kill_switch.py` — drawdown -6% → déclenché, 3 pertes → pause, PM_FEED stale → stop, reset minuit |

---

#### POLY-022 — Create POLY_RISK_GUARDIAN

| | |
|---|---|
| Type | `risk` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — calcul exposure, corrélation |
| Risque | **LOW** |
| Priorité | P0 |

**Objectif** : protection portefeuille (exposure, positions, corrélation). Scope = portefeuille global.

**Dépendances** : POLY-015

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_risk_guardian.py` |
| Test | `tests/test_risk_guardian.py` — 5 positions → bloqué, exposure 81% → bloqué |

---

#### POLY-023 — Create POLY_GLOBAL_RISK_GUARD

| | |
|---|---|
| Type | `risk` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — 4 niveaux, calcul perte cumulée |
| Risque | **HIGH** — safety-critical : erreur = système ne coupe pas à 4 000€ |
| Priorité | P0 |

**Objectif** : plafond perte cumulée 4 000€. Scope = système entier.

**Dépendances** : POLY-015, POLY-003

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_global_risk_guard.py` |
| State | `state/risk/global_risk_state.json` |
| Test | `tests/test_global_risk_guard.py` — pertes progressives → vérifier chaque transition NORMAL/ALERTE/CRITIQUE/ARRÊT TOTAL |

---

#### POLY-024 — Create POLY_CAPITAL_MANAGER

| | |
|---|---|
| Type | `risk` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — création accounts live, vérification pré-trade |
| Risque | **MED** — doit créer le compte live UNIQUEMENT après promotion:approved |
| Priorité | P0 |

**Objectif** : gestion accounts. Crée comptes live après Promotion Gate approve.

**Dépendances** : POLY-015, POLY-023, POLY-003

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_capital_manager.py` |
| Test | `tests/test_capital_manager.py` — promotion:approved → account créé, trade > capital → bloqué, stratégie stoppée → capital récupéré |

---

#### POLY-025 — Create POLY_PERFORMANCE_LOGGER

| | |
|---|---|
| Type | `evaluation` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — calcul métriques financières (Sharpe, PF, MDD) |
| Risque | **LOW** |
| Priorité | P1 |

**Objectif** : agréger métriques de performance. Déclencher milestones.

**Dépendances** : POLY-015, POLY-003

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_performance_logger.py` |
| State | `dashboard-data/aggregates/poly_paper_stats.json`, `poly_live_stats.json` |
| Test | `tests/test_performance_logger.py` — 50 trades simulés → WR/Sharpe/PF calculés, milestone 50 émis |

---

#### POLY-026 — Create POLY_STRATEGY_EVALUATOR

| | |
|---|---|
| Type | `evaluation` |
| Status | `todo` |
| Taille | **L** (2-3 jours) |
| Difficulté | **HIGH** — 8 axes de scoring, verdicts, classement normalisé |
| Risque | **MED** — la qualité de l'évaluation dépend de la quantité de trades paper accumulés |
| Priorité | P1 |

**Objectif** : score 8 axes, verdicts STAR/SOLID/FRAGILE/DECLINING/RETIRE, classement normalisé.

**Dépendances** : POLY-015, POLY-025, POLY-014

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_strategy_evaluator.py` |
| State | `state/evaluation/strategy_scores.json`, `state/evaluation/strategy_rankings.json` |
| Config | `references/evaluator_weights.json` (poids des 8 axes) |
| Test | `tests/test_strategy_evaluator.py` — Sharpe 2.5 + WR 85% → score > 70, Sharpe 0.5 + WR 45% → score < 40 |

---

#### POLY-027 — Create POLY_DECAY_DETECTOR

| | |
|---|---|
| Type | `evaluation` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — rolling 7j/30j sur 8 métriques |
| Risque | **LOW** |
| Priorité | P1 |

**Objectif** : détecter l'usure des stratégies. Rolling 7j vs 30j.

**Dépendances** : POLY-015, POLY-025

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_decay_detector.py` |
| State | `state/evaluation/decay_alerts.json` |
| Test | `tests/test_decay_detector.py` — WR chute 7% → WARNING, 3 métriques en déclin → CRITICAL |

---

### PHASE 6 — ADDITIONAL STRATEGIES

Patron identique à POLY-019/020 pour chaque ticket.

| Ticket | Agent | Type | Taille | Difficulté | Risque | Artifacts Python | Test |
|---|---|---|---|---|---|---|---|
| POLY-028 | POLY_LATENCY_ARB | `strategy` | M | HIGH (< 1s cycle) | HIGH (concurrence bots) | `strategies/poly_latency_arb.py` | `tests/test_latency_arb.py` |
| POLY-029 | POLY_BROWNIAN_SNIPER | `strategy` | M | HIGH (Brownian Motion) | MED | `strategies/poly_brownian_sniper.py` | `tests/test_brownian_sniper.py` |
| POLY-030 | POLY_PAIR_COST | `strategy` | M | MED | LOW | `strategies/poly_pair_cost.py` | `tests/test_pair_cost.py` |
| POLY-031 | POLY_OPP_SCORER | `strategy` | M | MED (LLM Sonnet) | MED (coût LLM) | `strategies/poly_opp_scorer.py` | `tests/test_opp_scorer.py` |
| POLY-032 | POLY_NO_SCANNER | `strategy` | S | LOW | LOW | `strategies/poly_no_scanner.py` | `tests/test_no_scanner.py` |
| POLY-033 | POLY_CONVERGENCE_STRAT | `strategy` | M | MED | LOW | `strategies/poly_convergence_strat.py` | `tests/test_convergence_strat.py` |
| POLY-034 | POLY_NEWS_STRAT | `strategy` | M | MED (intégration NEWS_SCORING) | MED | `strategies/poly_news_strat.py` | `tests/test_news_strat.py` |

Status : tous `todo`. Priorité : tous P1. Dépendances : Phases 1-5 complètes.

---

### PHASE 7 — ORCHESTRATION & LIVE

---

#### POLY-035 — Create POLY_FACTORY_ORCHESTRATOR

| | |
|---|---|
| Type | `infra` |
| Status | `todo` |
| Taille | **XL** (4-6 jours) |
| Difficulté | **HIGH** — state machine complète, 5 cycles, routing bus, chaîne de 7 filtres |
| Risque | **HIGH** — c'est le cerveau du système, tout passe par lui |
| Priorité | P0 |

**Objectif** : chef d'orchestre. State machine, cycles, routing.

**Dépendances** : POLY-003, POLY-014, POLY-015, POLY-002

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_factory_orchestrator.py` |
| State | `state/orchestrator/system_state.json`, `strategy_lifecycle.json`, `cycle_log.json` |
| Config | `references/nightly_schedule.json`, `references/filter_chain_order.json` |
| Test | `tests/test_orchestrator.py` — signal → 7 filtres, state machine transitions, cycle nightly séquence |

---

#### POLY-036 — Create POLY_STRATEGY_PROMOTION_GATE

| | |
|---|---|
| Type | `risk` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — 10 checks séquentiels |
| Risque | **HIGH** — safety-critical : un check manqué = stratégie promue sans validation complète |
| Priorité | P0 |

**Objectif** : 10 checks paper → live. Gate DÉCIDE, Capital Manager EXÉCUTE.

**Dépendances** : POLY-014, POLY-015, POLY-023, POLY-002

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_strategy_promotion_gate.py` |
| Test | `tests/test_promotion_gate.py` — 10/10 OK → approved, check 8 échoue → denied, vérifier que Gate ne crée AUCUN account |

---

#### POLY-037 — Create POLY_EXECUTION_ROUTER

| | |
|---|---|
| Type | `execution` |
| Status | `todo` |
| Taille | **S** (< 0.5 jour) |
| Difficulté | **LOW** — < 50 lignes de logique |
| Risque | **HIGH** — un bug ici route un signal paper vers le moteur live |
| Priorité | P0 |

**Objectif** : routeur trivial paper/live basé sur statut Registry.

**Dépendances** : POLY-014, POLY-003

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_execution_router.py` |
| Test | `tests/test_execution_router.py` — paper → execute:paper, active → execute:live, paused → erreur logguée |

---

#### POLY-038 — Create POLY_LIVE_EXECUTION_ENGINE

| | |
|---|---|
| Type | `execution` |
| Status | `todo` |
| Taille | **XL** (4-5 jours) |
| Difficulté | **HIGH** — on-chain, fills partiels, retries, slippage réel, gas |
| Risque | **HIGH** — capital réel en jeu, API Polymarket instable, transactions on-chain irréversibles |
| Priorité | P0 |

**Objectif** : exécution réelle on-chain via py-clob-client. MODULE SÉPARÉ du paper.

**Dépendances** : POLY-004, POLY-018, POLY-015, POLY-002

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_live_execution_engine.py` |
| State | `state/trading/live_trades_log.jsonl` |
| Env | `.env` : POLYMARKET_API_KEY, POLYMARKET_API_SECRET, WALLET_PRIVATE_KEY |
| Test | `tests/test_live_execution.py` — mock API submit, timeout → 3 retries → abandon, payload live_executed conforme |

---

#### POLY-039 — Create POLY_COMPOUNDER

| | |
|---|---|
| Type | `evaluation` |
| Status | `todo` |
| Taille | **M** (1-2 jours) |
| Difficulté | **MED** — analyse trades via Haiku |
| Risque | **LOW** |
| Priorité | P2 |

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_compounder.py` |
| State | `memory/learnings/polymarket_{date}.json` |
| Test | `tests/test_compounder.py` |

---

#### POLY-040 — Create POLY_STRATEGY_TUNER

| | |
|---|---|
| Type | `evaluation` |
| Status | `todo` |
| Taille | **L** (2-3 jours) |
| Difficulté | **HIGH** — analyse multi-dimensionnelle, recommandations |
| Risque | **MED** |
| Priorité | P2 |

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_strategy_tuner.py` |
| State | `state/evaluation/tuning_recommendations.json` |
| Test | `tests/test_strategy_tuner.py` |

---

#### POLY-041 — Create POLY_STRATEGY_SCOUT

| | |
|---|---|
| Type | `evaluation` |
| Status | `todo` |
| Taille | **L** (2-3 jours) |
| Difficulté | **MED** — scraping + évaluation viabilité via Sonnet |
| Risque | **MED** — qualité scraping dépend des sources externes |
| Priorité | P2 |

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_strategy_scout.py` |
| State | `state/research/scouted_strategies.json` |
| Test | `tests/test_strategy_scout.py` |

---

### PHASE 8 — MONITORING

---

#### POLY-042 — Create POLY_SYSTEM_MONITOR

| | |
|---|---|
| Type | `infra` |
| Status | `todo` |
| Taille | **L** (2-3 jours) |
| Difficulté | **MED** — surveillance multi-couche (agents, APIs, VPS, cohérence) |
| Risque | **LOW** |
| Priorité | P1 |

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_system_monitor.py` |
| Config | `references/monitoring_thresholds.json` |
| Test | `tests/test_system_monitor.py` — agent down → alerte, API latence 3× → warning |

---

#### POLY-043 — Create POLY_HEARTBEAT

| | |
|---|---|
| Type | `infra` |
| Status | `todo` |
| Taille | **S** (< 1 jour) |
| Difficulté | **LOW** — pattern existant OpenClaw |
| Risque | **LOW** |
| Priorité | P2 |

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `poly_heartbeat.py` |
| Test | `tests/test_heartbeat.py` |

---

### PHASE 9 — MULTI-PLATFORM

---

#### POLY-044 — Create connector_kalshi

| | |
|---|---|
| Type | `data` |
| Status | `todo` |
| Taille | **L** (2-3 jours) |
| Difficulté | **MED** |
| Risque | **MED** — API Kalshi non testée |
| Priorité | P2 |

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `connectors/connector_kalshi.py` |
| Test | `tests/test_connector_kalshi.py` |

---

#### POLY-045 — Create connector_sportsbook

| | |
|---|---|
| Type | `data` |
| Status | `todo` |
| Taille | **L** (2-3 jours) |
| Difficulté | **MED** — odds conversion |
| Risque | **MED** |
| Priorité | P2 |

**Artifacts** :

| Type | Fichier |
|---|---|
| Python | `connectors/connector_sportsbook.py` |
| Test | `tests/test_connector_sportsbook.py` |

---

## 4. DÉPENDANCES ENTRE TICKETS

```
POLY-001 (Data Store) ─ S, LOW, LOW
  ├── POLY-002 (Audit Log) ─ S, LOW, LOW
  │     └── POLY-003 (Bus) ─ L, MED, MED
  │           ├── POLY-004 (Market Connector) ─ L, HIGH, HIGH
  │           │     └── POLY-010 (Market Structure) ─ M, MED, LOW
  │           ├── POLY-005 (Binance Feed) ─ M, MED, MED
  │           │     └── POLY-009 (Binance Signals) ─ M, MED, LOW
  │           ├── POLY-006 (NOAA Feed) ─ S, LOW, MED
  │           └── POLY-007 (Wallet Feed) ─ M, MED, MED
  │                 └── POLY-011 (Wallet Tracker) ─ M, MED, LOW
  │
  ├── POLY-008 (Data Validator) ─ M, MED, LOW
  ├── POLY-012 (Market Analyst) ─ M, MED, MED
  ├── POLY-013 (Backtest Engine) ─ L, MED, MED
  │
  ├── POLY-014 (Registry) ─ M, LOW, LOW
  │     └── POLY-015 (Account) ─ M, MED, LOW
  │           ├── POLY-016 (Kelly Sizer) ─ S, LOW, LOW
  │           ├── POLY-017 (Paper Execution) ─ M, MED, HIGH ⚠️ SÉCURITÉ
  │           ├── POLY-018 (Order Splitter) ─ S, LOW, LOW
  │           ├── POLY-019 (Arb Scanner) ─ M, MED, MED
  │           └── POLY-020 (Weather Arb) ─ M, MED, MED
  │
  ├── POLY-021 (Kill Switch) ─ L, HIGH, HIGH ⚠️ SÉCURITÉ
  ├── POLY-022 (Risk Guardian) ─ M, MED, LOW
  ├── POLY-023 (Global Risk Guard) ─ M, MED, HIGH ⚠️ SÉCURITÉ
  ├── POLY-024 (Capital Manager) ─ M, MED, MED
  ├── POLY-025 (Performance Logger) ─ M, MED, LOW
  ├── POLY-026 (Strategy Evaluator) ─ L, HIGH, MED
  ├── POLY-027 (Decay Detector) ─ M, MED, LOW
  │
  ├── POLY-035 (Orchestrator) ─ XL, HIGH, HIGH
  ├── POLY-036 (Promotion Gate) ─ M, MED, HIGH ⚠️ SÉCURITÉ
  ├── POLY-037 (Execution Router) ─ S, LOW, HIGH ⚠️ SÉCURITÉ
  ├── POLY-038 (Live Execution) ─ XL, HIGH, HIGH ⚠️ SÉCURITÉ
  │
  └── POLY-042 (System Monitor) ─ L, MED, LOW
```

**Chemin critique** : POLY-001 → 002 → 003 → 004 → 010 → 015 → 017 → 019 → (Phase 5) → 035 → 036 → 038

**Tickets à plus haut risque** : POLY-004 (WebSocket Polymarket), POLY-021 (Kill Switch), POLY-035 (Orchestrator), POLY-038 (Live Execution)

---

## 5. TICKETS CRITIQUES DE SÉCURITÉ

**Non négociables avant tout passage au live.**

| Ticket | Composant | Difficulté | Risque | Vérification clé |
|---|---|---|---|---|
| POLY-017 | PAPER_EXECUTION_ENGINE | MED | HIGH | `grep py-clob-client` → 0 résultats |
| POLY-021 | KILL_SWITCH | HIGH | HIGH | 5 niveaux testés, drawdown -6% → stop |
| POLY-022 | RISK_GUARDIAN | MED | LOW | 5 positions → bloqué |
| POLY-023 | GLOBAL_RISK_GUARD | MED | HIGH | Perte 4 000€ → ARRÊT TOTAL vérifié |
| POLY-036 | PROMOTION_GATE | MED | HIGH | 10 checks testés, Gate ne crée aucun account |
| POLY-037 | EXECUTION_ROUTER | LOW | HIGH | < 50 lignes, routing vérifié |
| POLY-038 | LIVE_EXECUTION_ENGINE | HIGH | HIGH | Module séparé, retries testés |
| POLY-002 | AUDIT_LOG | LOW | LOW | Append-only vérifié |
| POLY-008 | DATA_VALIDATOR | MED | LOW | Prix 0.00 → SUSPECT vérifié |

---

## 6. TICKETS DE TEST ET VALIDATION

---

#### POLY-T01 — Tests unitaires data

| | |
|---|---|
| Type | `test` |
| Status | `todo` |
| Taille | **M** |
| Scope | DATA_STORE, AUDIT_LOG, Bus, DATA_VALIDATOR |

**Artifacts** : `tests/test_data_store.py`, `tests/test_audit_log.py`, `tests/test_event_bus.py`, `tests/test_data_validator.py`

**Tests** : read/write ctx.state, JSON Lines integrity, event publish/poll/ack, validation rules

---

#### POLY-T02 — Tests unitaires signal

| | |
|---|---|
| Type | `test` |
| Status | `todo` |
| Taille | **M** |
| Scope | BINANCE_SIGNALS, MARKET_STRUCTURE_ANALYZER, WALLET_TRACKER, MARKET_ANALYST |

**Artifacts** : `tests/test_binance_signals.py`, `tests/test_market_structure.py`, `tests/test_wallet_tracker.py`, `tests/test_market_analyst.py`

---

#### POLY-T03 — Tests bus et idempotence

| | |
|---|---|
| Type | `test` |
| Status | `todo` |
| Taille | **M** |
| Scope | Bus de communication |

**Artifacts** : `tests/test_bus_idempotence.py`

**Tests** : 1000 events → tous présents, replay event_id → ignoré, 3 échecs → dead_letter, priority high → premier, mode écrasement

---

#### POLY-T04 — Tests paper trading end-to-end

| | |
|---|---|
| Type | `test` |
| Status | `blocked` (attend Phases 1-4) |
| Taille | **L** |
| Scope | signal → 7 filtres → paper execution → account update |

**Artifacts** : `tests/test_paper_e2e.py`

**Tests** : arb → filtres → trade → account MAJ, marché illiquide → rejeté filtre 1, marché ambigu → rejeté filtre 2

---

#### POLY-T05 — Tests garde-fous

| | |
|---|---|
| Type | `test` |
| Status | `blocked` (attend Phase 5) |
| Taille | **L** |
| Scope | KILL_SWITCH, RISK_GUARDIAN, GLOBAL_RISK_GUARD, PROMOTION_GATE |

**Artifacts** : `tests/test_guards.py`

**Tests** : drawdown -6% → kill switch, 6ème position → bloqué, perte 4 000€ → arrêt total, approval expiré → denied

---

#### POLY-T06 — Tests échec API

| | |
|---|---|
| Type | `test` |
| Status | `blocked` (attend Phase 7) |
| Taille | **M** |
| Scope | MARKET_CONNECTOR, BINANCE_FEED, LIVE_EXECUTION_ENGINE |

**Artifacts** : `tests/test_api_failures.py`

**Tests** : WS disconnect → reconnexion, API 5xx → retry, 3 retries → dead letter, gas insuffisant → alerte

---

#### POLY-T07 — Tests redémarrage et reprise

| | |
|---|---|
| Type | `test` |
| Status | `blocked` (attend Phase 8) |
| Taille | **M** |
| Scope | Tous les agents |

**Artifacts** : `tests/test_restart.py`

**Tests** : kill PM2 → restart auto, crash mid-trade → pas de trade dupliqué, restart → feeds reprennent < 60s

---

## 7. ORDRE RECOMMANDÉ DE RÉALISATION

### Séquentiel obligatoire

```
POLY-001 (S) → POLY-002 (S) → POLY-003 (L) → Phase 1 feeds en parallèle
```

### Parallélisable après le socle

```
Fil A : POLY-004 (L) + POLY-005 (M)     — feeds WebSocket
Fil B : POLY-006 (S) + POLY-007 (M)     — feeds REST
Fil C : POLY-014 (M) + POLY-015 (M)     — registry + accounts
```

### Dépendances inter-phases

```
Phase 2 attend Phase 1 (données à valider)
Phase 3 attend Phase 1+2 (données historiques)
Phase 4 attend Phase 2+3 (signaux + calibration)
Phase 5 attend Phase 4 (trades à protéger)
Phase 6 attend Phase 5 (risque en place)
Phase 7 attend Phase 6 + 14 jours de paper réussi
Phase 8 attend Phase 7 (système à surveiller)
```

---

## 8. SPRINT 1 RECOMMANDÉ

### Objectif

Fondations : données affluent, bus opérationnel, audit log fonctionne. Zéro trading.

### Tickets

| Ticket | Composant | Type | Taille | Difficulté | Risque |
|---|---|---|---|---|---|
| POLY-001 | DATA_STORE | infra | M | LOW | LOW |
| POLY-002 | AUDIT_LOG | infra | S | LOW | LOW |
| POLY-003 | Event Bus | infra | L | MED | MED |
| POLY-004 | MARKET_CONNECTOR | data | L | HIGH | HIGH |
| POLY-005 | BINANCE_FEED | data | M | MED | MED |
| POLY-006 | NOAA_FEED | data | S | LOW | MED |
| POLY-007 | WALLET_FEED | data | M | MED | MED |

**Effort total Sprint 1** : ~8-14 jours selon expérience API.

**Ticket le plus risqué** : POLY-004 (WebSocket Polymarket, reconnexion, rate limits). Commencer tôt.

### Définition de Done

```
✓ state/ arborescence complète sur VPS
✓ polymarket_prices.json mis à jour en continu (WebSocket)
✓ binance_raw.json mis à jour en continu (WebSocket)
✓ noaa_forecasts.json mis à jour toutes les 2 min
✓ wallet_raw_positions.json mis à jour toutes les 60s
✓ audit log contient les events de connexion
✓ bus pending_events.jsonl contient les events feed:*
✓ PM2 gère tous les processus
✓ Tourne 24h sans crash
✓ tests/test_data_store.py + tests/test_audit_log.py + tests/test_event_bus.py passent
```

### Prérequis

```
✓ VPS Hostinger opérationnel (Ubuntu 24, Python 3.11+, PM2, Node.js)
✓ Clé API Polymarket + Binance (lecture seule)
✓ Polygon RPC (QuickNode free tier)
✓ Workspace OpenClaw POLY_FACTORY initialisé
```

---

## ANNEXE — VUE SYNTHÉTIQUE DE TOUS LES TICKETS

| ID | Composant | Type | Taille | Difficulté | Risque | Priorité | Status |
|---|---|---|---|---|---|---|---|
| 001 | DATA_STORE | infra | M | LOW | LOW | P0 | todo |
| 002 | AUDIT_LOG | infra | S | LOW | LOW | P0 | todo |
| 003 | Event Bus | infra | L | MED | MED | P0 | todo |
| 004 | MARKET_CONNECTOR | data | L | HIGH | HIGH | P0 | todo |
| 005 | BINANCE_FEED | data | M | MED | MED | P0 | todo |
| 006 | NOAA_FEED | data | S | LOW | MED | P1 | todo |
| 007 | WALLET_FEED | data | M | MED | MED | P1 | todo |
| 008 | DATA_VALIDATOR | data | M | MED | LOW | P0 | todo |
| 009 | BINANCE_SIGNALS | signal | M | MED | LOW | P1 | todo |
| 010 | MARKET_STRUCTURE | signal | M | MED | LOW | P0 | todo |
| 011 | WALLET_TRACKER | signal | M | MED | LOW | P1 | todo |
| 012 | MARKET_ANALYST | signal | M | MED | MED | P1 | todo |
| 013 | BACKTEST_ENGINE | evaluation | L | MED | MED | P1 | todo |
| 014 | STRATEGY_REGISTRY | infra | M | LOW | LOW | P0 | todo |
| 015 | STRATEGY_ACCOUNT | infra | M | MED | LOW | P0 | todo |
| 016 | KELLY_SIZER | risk | S | LOW | LOW | P1 | todo |
| 017 | PAPER_EXECUTION | execution | M | MED | HIGH | P0 | todo |
| 018 | ORDER_SPLITTER | execution | S | LOW | LOW | P1 | todo |
| 019 | ARB_SCANNER | strategy | M | MED | MED | P0 | todo |
| 020 | WEATHER_ARB | strategy | M | MED | MED | P1 | todo |
| 021 | KILL_SWITCH | risk | L | HIGH | HIGH | P0 | todo |
| 022 | RISK_GUARDIAN | risk | M | MED | LOW | P0 | todo |
| 023 | GLOBAL_RISK_GUARD | risk | M | MED | HIGH | P0 | todo |
| 024 | CAPITAL_MANAGER | risk | M | MED | MED | P0 | todo |
| 025 | PERFORMANCE_LOGGER | evaluation | M | MED | LOW | P1 | todo |
| 026 | STRATEGY_EVALUATOR | evaluation | L | HIGH | MED | P1 | todo |
| 027 | DECAY_DETECTOR | evaluation | M | MED | LOW | P1 | todo |
| 028 | LATENCY_ARB | strategy | M | HIGH | HIGH | P1 | todo |
| 029 | BROWNIAN_SNIPER | strategy | M | HIGH | MED | P1 | todo |
| 030 | PAIR_COST | strategy | M | MED | LOW | P1 | todo |
| 031 | OPP_SCORER | strategy | M | MED | MED | P1 | todo |
| 032 | NO_SCANNER | strategy | S | LOW | LOW | P1 | todo |
| 033 | CONVERGENCE_STRAT | strategy | M | MED | LOW | P1 | todo |
| 034 | NEWS_STRAT | strategy | M | MED | MED | P1 | todo |
| 035 | ORCHESTRATOR | infra | XL | HIGH | HIGH | P0 | todo |
| 036 | PROMOTION_GATE | risk | M | MED | HIGH | P0 | todo |
| 037 | EXECUTION_ROUTER | execution | S | LOW | HIGH | P0 | todo |
| 038 | LIVE_EXECUTION | execution | XL | HIGH | HIGH | P0 | todo |
| 039 | COMPOUNDER | evaluation | M | MED | LOW | P2 | todo |
| 040 | STRATEGY_TUNER | evaluation | L | HIGH | MED | P2 | todo |
| 041 | STRATEGY_SCOUT | evaluation | L | MED | MED | P2 | todo |
| 042 | SYSTEM_MONITOR | infra | L | MED | LOW | P1 | todo |
| 043 | HEARTBEAT | infra | S | LOW | LOW | P2 | todo |
| 044 | connector_kalshi | data | L | MED | MED | P2 | todo |
| 045 | connector_sportsbook | data | L | MED | MED | P2 | todo |
| T01 | Tests data | test | M | — | — | P0 | todo |
| T02 | Tests signal | test | M | — | — | P1 | todo |
| T03 | Tests bus | test | M | — | — | P0 | todo |
| T04 | Tests paper e2e | test | L | — | — | P1 | blocked |
| T05 | Tests garde-fous | test | L | — | — | P0 | blocked |
| T06 | Tests échec API | test | M | — | — | P1 | blocked |
| T07 | Tests restart | test | M | — | — | P1 | blocked |

**Totaux** : 45 dev + 7 test = **52 tickets**. 18 P0, 24 P1, 10 P2. 7 tickets HIGH risk (⚠️ sécurité).

---

*Backlog v2 basé sur ARCHITECTURE v4.0, PIPELINE v4.0, IMPLEMENTATION_PLAN v3.0.*
*52 tickets avec estimation fine, type/status, et artifacts systématiques. Prêt pour Claude Code.*
