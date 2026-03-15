# bus_events.md — Inventaire des topics bus Trading Factory

**Date** : 2026-03-15
**Scope** : Bus JSONL file-based (`state/trading/bus/`)

---

## Architecture du bus

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Type | File-based JSONL (1 fichier par topic) | [OBSERVÉ] |
| Répertoire | `state/trading/bus/` | [OBSERVÉ] |
| Format envelope | `{event_id, topic, timestamp, producer, payload}` | [OBSERVÉ] |
| Consommation | Cursor-based (`readSince`), chaque agent maintient son offset | [OBSERVÉ] |
| Taille totale | ~170 Mo (18 fichiers) | [OBSERVÉ] |
| Rotation | `bus_rotation.js` → archive + truncate (daily 03:00 UTC) | [OBSERVÉ] |
| Cleanup | `bus_cleanup_trading.js` → TTL-based pruning (daily 03:30 UTC) | [OBSERVÉ] |

---

## Inventaire des topics

### Layer 1 — Raw Data (temps réel, TTL 0.25–2 jours)

| Topic | Fichier JSONL | Taille | Producteur | Consommateur(s) | Tag |
|-------|---------------|--------|------------|------------------|-----|
| `trading.raw.market.ticker` | 18.2 Mo | BINANCE_PRICE_FEED | (aucun via bus — MARKET_EYE fetch direct) | [OBSERVÉ] |
| `trading.raw.market.ohlcv` | 0 octets | (désactivé) | — | [OBSERVÉ] |
| `trading.raw.news.article` | 272.9 Ko | NEWS_FEED | NEWS_SCORING | [OBSERVÉ] |
| `trading.raw.social.post` | 2.4 Ko | NEWS_FEED (Fear&Greed) | NEWS_SCORING | [OBSERVÉ] |
| `trading.raw.whale.transfer` | 421.3 Ko | WHALE_FEED | WHALE_ANALYZER | [OBSERVÉ] |

### Layer 2 — Intelligence (signal processing, TTL 3–90 jours)

| Topic | Fichier JSONL | Taille | Producteur | Consommateur(s) | Tag |
|-------|---------------|--------|------------|------------------|-----|
| `trading.intel.market.features` | **71.8 Mo** | MARKET_EYE | PREDICTOR, REGIME_DETECTOR, TRADE_GENERATOR | [OBSERVÉ] |
| `trading.intel.prediction` | 7.7 Mo | PREDICTOR | ⚠️ **AUCUN** | [OBSERVÉ] |
| `trading.intel.news.event` | 8.8 Mo | NEWS_SCORING | TRADE_GENERATOR | [OBSERVÉ] |
| `trading.intel.whale.signal` | 3.1 Mo | WHALE_ANALYZER | REGIME_DETECTOR | [OBSERVÉ] |
| `trading.intel.regime` | 11.3 Mo | REGIME_DETECTOR | TRADE_GENERATOR | [OBSERVÉ] |

### Layer 3 — Strategy (prise de décision, TTL 90–365 jours)

| Topic | Fichier JSONL | Taille | Producteur | Consommateur(s) | Tag |
|-------|---------------|--------|------------|------------------|-----|
| `trading.strategy.trade.proposal` | 3.9 Mo | TRADE_GENERATOR | RISK_MANAGER | [OBSERVÉ] |
| `trading.strategy.order.plan` | 154.4 Ko | RISK_MANAGER | POLICY_ENGINE, TRADING_ORCHESTRATOR | [OBSERVÉ] |
| `trading.strategy.policy.decision` | 154.7 Ko | POLICY_ENGINE | TRADING_ORCHESTRATOR | [OBSERVÉ] |
| `trading.strategy.block` | 1.6 Ko | RISK_MANAGER (rejets) | (aucun consommateur runtime) | [OBSERVÉ] |

### Layer 4 — Execution (ordres + fills, TTL 90 jours–∞)

| Topic | Fichier JSONL | Taille | Producteur | Consommateur(s) | Tag |
|-------|---------------|--------|------------|------------------|-----|
| `trading.exec.order.submit` | (dans pipeline_state) | — | TRADING_ORCHESTRATOR | TESTNET_EXECUTOR, PAPER_EXECUTOR | [OBSERVÉ] |
| `trading.exec.trade.ledger` | 5.4 Ko | TESTNET_EXECUTOR, PAPER_EXECUTOR | PERFORMANCE_ANALYST, KILL_SWITCH_GUARDIAN, TRADING_PUBLISHER, TRADE_STRATEGY_TUNER | [OBSERVÉ] |
| `trading.exec.position.snapshot` | 10.2 Mo | TESTNET_EXECUTOR, PAPER_EXECUTOR | (monitoring) | [OBSERVÉ] |

### Layer 5 — Ops & Alertes (TTL 90 jours, pas d'auto-delete)

| Topic | Fichier JSONL | Taille | Producteur | Consommateur(s) | Tag |
|-------|---------------|--------|------------|------------------|-----|
| `trading.ops.killswitch.state` | 8.4 Mo | KILL_SWITCH_GUARDIAN | (monitoring, alerte Telegram) | [OBSERVÉ] |
| `trading.ops.alert` | (dans killswitch) | — | KILL_SWITCH_GUARDIAN, NEWS_SCORING | (Telegram) | [OBSERVÉ] |

---

## Topics orphelins

| Topic | Producteur | Problème | Sévérité | Tag |
|-------|------------|----------|----------|-----|
| `trading.intel.prediction` | PREDICTOR (11 093 runs) | **Aucun consommateur identifié** — TRADE_GENERATOR lit features + regime + news, pas prediction | MOYEN | [DÉDUIT] |
| `trading.raw.market.ticker` | BINANCE_PRICE_FEED | **Consommateur indirect** — MARKET_EYE fetch directement Binance API, ne lit pas ce topic | FAIBLE | [DÉDUIT] |
| `trading.raw.market.ohlcv` | (désactivé) | Fichier vide, topic jamais alimenté | INFO | [OBSERVÉ] |
| `trading.strategy.block` | RISK_MANAGER | Écrit les rejets mais **aucun agent ne les consomme** — audit trail seulement | INFO | [DÉDUIT] |

**Impact cumulé** : PREDICTOR tourne 11 093 fois (60s cycle) et produit 7.7 Mo de données que personne ne lit. Coût CPU pur (pas de LLM). [DÉDUIT]

---

## Flux ASCII du bus

```
┌──────────────────────────── EXTERNAL APIS ─────────────────────────────┐
│  Binance REST    Etherscan v2    RSS/CryptoPanic    Reddit   F&G     │
└───┬──────────────────┬──────────────────┬──────────────┬──────────────┘
    │                  │                  │              │
    ▼                  ▼                  ▼              │
┌─ LAYER 1: RAW ──────────────────────────────────────────────────────┐
│                                                                      │
│  BINANCE_PRICE_FEED ──→ trading.raw.market.ticker (18 Mo)           │
│                          ⚠️ pas consommé via bus                     │
│                                                                      │
│  WHALE_FEED ──→ trading.raw.whale.transfer (421 Ko)                 │
│                          │                                           │
│  NEWS_FEED ──→ trading.raw.news.article (273 Ko)                    │
│            └─→ trading.raw.social.post (2 Ko)                       │
│                          │                                           │
└──────────────────────────┼───────────────────────────────────────────┘
                           ▼
┌─ LAYER 2: INTELLIGENCE ─────────────────────────────────────────────┐
│                                                                      │
│  MARKET_EYE ──→ trading.intel.market.features (72 Mo) ──┬──→ PRED  │
│  (fetch direct Binance, pas bus)                         ├──→ REGIME│
│                                                          └──→ TGEN  │
│                                                                      │
│  PREDICTOR ──→ trading.intel.prediction (7.7 Mo) ──→ ⚠️ ORPHELIN   │
│                                                                      │
│  NEWS_SCORING ──→ trading.intel.news.event (8.8 Mo) ──→ TGEN       │
│               └─→ trading.ops.alert (urgency ≥9)                    │
│                                                                      │
│  WHALE_ANALYZER ──→ trading.intel.whale.signal (3.1 Mo) ──→ REGIME │
│                                                                      │
│  REGIME_DETECTOR ──→ trading.intel.regime (11.3 Mo) ──→ TGEN       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                           ▼
┌─ LAYER 3: STRATEGY ─────────────────────────────────────────────────┐
│                                                                      │
│  TRADE_GENERATOR ──→ trading.strategy.trade.proposal (3.9 Mo)       │
│  (Haiku LLM)               │                                        │
│                             ▼                                        │
│  RISK_MANAGER ──┬─→ trading.strategy.order.plan (154 Ko) ──┬──→ PE │
│  (7 filtres)    │                                           └──→ ORC│
│                 └─→ trading.strategy.block (1.6 Ko) ← rejects      │
│                                                                      │
│  POLICY_ENGINE ──→ trading.strategy.policy.decision (155 Ko)        │
│  (env=paper)            │                                            │
│                         ▼                                            │
└──────────────────────────────────────────────────────────────────────┘
                           ▼
┌─ LAYER 4: EXECUTION ────────────────────────────────────────────────┐
│                                                                      │
│  TRADING_ORCHESTRATOR ──→ trading.exec.order.submit                 │
│  (corrèle plan+decision)     │                                       │
│  ⚠️ 95 HUMAN_APPROVAL=EXPIRED │                                     │
│                              ▼                                       │
│  TESTNET_EXECUTOR ──┬─→ trading.exec.trade.ledger (5.4 Ko)         │
│  (Binance Testnet)  └─→ trading.exec.position.snapshot (10 Mo)     │
│                                                                      │
│  PAPER_EXECUTOR ──┬─→ trading.exec.trade.ledger                    │
│  (désactivé)      └─→ trading.exec.position.snapshot               │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                           ▼
┌─ LAYER 5: OPS & REPORTING ──────────────────────────────────────────┐
│                                                                      │
│  KILL_SWITCH_GUARDIAN ──→ trading.ops.killswitch.state (8.4 Mo)     │
│  (⚠️ 27k erreurs)    └─→ trading.ops.alert                         │
│                                                                      │
│  TRADING_PUBLISHER     ← reads trade.ledger → Telegram             │
│  GLOBAL_TOKEN_TRACKER  ← reads token_costs.jsonl → Telegram        │
│  POLY_TRADING_PUBLISHER ← reads POLY_FACTORY state → Telegram      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Analyse de résilience

### Scénario 1 : Perte d'un topic (fichier supprimé)

| Topic perdu | Impact | Récupération | Tag |
|-------------|--------|-------------|-----|
| `trading.intel.market.features` | **BLOQUANT** — PREDICTOR, REGIME_DETECTOR, TRADE_GENERATOR ne reçoivent plus d'inputs | Recréation automatique par MARKET_EYE au prochain cycle (15s) | [DÉDUIT] |
| `trading.strategy.trade.proposal` | Pipeline arrêté — plus de nouveaux trades | Recréation par TRADE_GENERATOR (300s) | [DÉDUIT] |
| `trading.exec.trade.ledger` | Perte historique trades — PERFORMANCE_ANALYST, KILL_SWITCH_GUARDIAN perdent contexte | **Non récupérable** sauf backup | [DÉDUIT] |
| `trading.ops.killswitch.state` | Kill switch state perdu — reset implicite à ARMED | Régénéré par KILL_SWITCH_GUARDIAN (60s) | [DÉDUIT] |

### Scénario 2 : Agent non-consommant (arrêt d'un consommateur)

| Agent arrêté | Topics accumulés | Conséquence | Tag |
|-------------|------------------|-------------|-----|
| TRADE_GENERATOR | `intel.market.features` (72 Mo/semaine) | Pas de nouveaux signaux, positions existantes continuent via ORCHESTRATOR | [DÉDUIT] |
| RISK_MANAGER | `strategy.trade.proposal` (3.9 Mo/semaine) | Proposals s'accumulent, aucun ordre passé | [DÉDUIT] |
| TESTNET_EXECUTOR | `exec.order.submit` accumule | Ordres non exécutés, ORCHESTRATOR les expire (TTL 10 min) | [DÉDUIT] |
| KILL_SWITCH_GUARDIAN | `trade.ledger`, `ops.health` | **CRITIQUE** — pas de surveillance perte/erreurs, kill switch inopérant | [DÉDUIT] |

### Scénario 3 : Duplication (conflit C-02 — double poller)

| Composant | Risque | Probabilité | Tag |
|-----------|--------|------------|-----|
| BINANCE_PRICE_FEED | Double fetch → double events dans `raw.market.ticker` | ÉLEVÉ (2 pollers actifs) | [DÉDUIT] |
| MARKET_EYE | Double calcul → double events dans `intel.market.features` (accélère la croissance 72 Mo) | ÉLEVÉ | [DÉDUIT] |
| TRADE_GENERATOR | Double appel Haiku LLM → double coût ($0.98/jour au lieu de $0.49) + signaux dupliqués | ÉLEVÉ | [DÉDUIT] |
| RISK_MANAGER | Double validation → double proposals vers ORCHESTRATOR | MOYEN | [DÉDUIT] |
| TESTNET_EXECUTOR | Double ordres sur Binance Testnet | **CRITIQUE** | [DÉDUIT] |

**Mitigation observée** : Aucune déduplication au niveau du bus. Le poller.js utilise `lastRun[agent_id]` en mémoire → 2 instances = 2 lastRun indépendants → **aucune protection**. [DÉDUIT]

---

## Rétention par layer

| Layer | Topics | TTL (bus_cleanup) | Archive (bus_rotation) | Tag |
|-------|--------|-------------------|------------------------|-----|
| 1 — Live | `raw.*` | 0.25–2 jours | 7 jours | [OBSERVÉ] |
| 2 — Context | `intel.*` | 3–90 jours | 30 jours | [OBSERVÉ] |
| 3 — Learning | `strategy.*`, `exec.trade.ledger` | 90–365 jours | 30 jours | [OBSERVÉ] |
| 4 — Risk/Audit | `ops.*` | 90 jours (pas d'auto-delete) | Jamais | [OBSERVÉ] |

**Anomalie rétention** : `trading.ops.killswitch.state` fait 8.4 Mo malgré la rétention "pas d'auto-delete". Ce fichier grandit indéfiniment (1 event/60s × ~6 jours = 8 640 events). [DÉDUIT]

---

## Volumétrie

| Topic | Events/heure (estimé) | Taille/jour | Taille/semaine | Tag |
|-------|----------------------|-------------|----------------|-----|
| `intel.market.features` | ~720 (3 symbols × 3 TF × 4/min) | **~10 Mo** | **~72 Mo** | [DÉDUIT] |
| `raw.market.ticker` | ~360 | ~2.6 Mo | ~18 Mo | [DÉDUIT] |
| `intel.regime` | ~60 | ~1.6 Mo | ~11 Mo | [DÉDUIT] |
| `exec.position.snapshot` | ~120 | ~1.5 Mo | ~10 Mo | [DÉDUIT] |
| `ops.killswitch.state` | ~60 | ~1.2 Mo | ~8.4 Mo | [DÉDUIT] |
| Tous les autres | <60 | <1 Mo | <7 Mo | [DÉDUIT] |
| **TOTAL** | ~1 500 | **~17 Mo/jour** | **~120 Mo/semaine** | [DÉDUIT] |

**Projection 30 jours sans cleanup** : ~500 Mo. Avec cleanup actif : ~170 Mo stabilisé. [DÉDUIT]
