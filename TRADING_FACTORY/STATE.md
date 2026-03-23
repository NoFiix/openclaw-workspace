# TRADING_FACTORY/STATE.md — Sources de vérité

> Dernière mise à jour : Mars 2026
> Ce fichier liste tous les fichiers d'état de TRADING_FACTORY,
> leur rôle, qui les écrit, qui les lit, et s'ils sont source de vérité.

---

## RÈGLE FONDAMENTALE

`state/trading/` ne bouge jamais. C'est la mémoire vivante du système.
Toute donnée affichée dans le dashboard doit être tracée à un fichier de cette liste.

---

## STRUCTURE COMPLÈTE

```
state/trading/
├── bus/                    ← events JSONL (append-only)
├── schedules/              ← config schedules 24 agents
├── configs/                ← config stratégies, candidats, whale
├── strategies/             ← wallets et métriques par stratégie
│   ├── MeanReversion/
│   ├── Momentum/
│   ├── Breakout/
│   └── NewsTrading/
├── exec/                   ← positions et état exécution
├── learning/               ← analytics et coûts LLM
├── memory/                 ← état runtime agents (curseurs bus)
├── runs/                   ← runs éphémères
├── risk/                   ← état risque global
├── context/                ← contexte marché
├── audit/                  ← append-only, jamais purgé
└── poller.log              ← logs du poller
```

---

## FICHIERS D'ÉTAT CRITIQUES

### Wallets — source de vérité capital

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `strategies/*/wallet.json` | PAPER_EXECUTOR, TESTNET_EXECUTOR (via walletOnClose) | Dashboard, RISK_MANAGER | ✅ OUI |

**Structure wallet.json :**
```json
{
  "strategy_id": "MeanReversion",
  "initial_capital": 1000,
  "cash": 1000,
  "equity": 1000,
  "allocated": 0,
  "realized_pnl": 0,
  "roi_pct": 0,
  "trade_count": 0,
  "win_count": 0,
  "peak_equity": 1000,
  "max_drawdown": 0,
  "status": "active",
  "suspended_reason": null,
  "updated_at": "2026-03-21T..."
}
```

**⚠️ Règles critiques :**
- `cash` se met à jour UNIQUEMENT via `walletOnClose()`
- `walletOnOpen()` ne doit être appelé QUE si position confirmée ouverte
- Wallets actuellement à $1000 car `walletOnClose()` pas encore déclenché sur vrai trade — comportement normal

---

### Positions — source de vérité positions ouvertes

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `exec/positions_testnet.json` | TESTNET_EXECUTOR | Dashboard, RISK_MANAGER | ✅ OUI (testnet) |
| `exec/positions.json` | PAPER_EXECUTOR | Dashboard | ✅ OUI (paper) |
| `strategies/*/positions.json` | Executors | RISK_MANAGER | ✅ OUI (par stratégie) |

**⚠️ Dette technique :** Les positions globales (`exec/positions.json`) et
par stratégie (`strategies/*/positions.json`) coexistent.
Migration vers positions uniquement par stratégie prévue mais non urgente.

---

### Stratégies et candidats

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `configs/strategies_registry.json` | STRATEGY_SCOUT (via validateRegistry) | Tous agents | ✅ OUI — stratégies actives |
| `configs/candidates_pending.json` | STRATEGY_SCOUT | STRATEGY_SCOUT, Dashboard | ✅ OUI — candidats |

**Structure strategies_registry.json :**
```json
{
  "MeanReversion": {
    "enabled": true,
    "lifecycle_status": "paper_active",
    "execution_target": "paper",
    "wallet_mode": "virtual",
    "live_approved": false,
    "min_cash_threshold": 50
  }
}
```

**Lifecycle statuts :**
- `paper_active` — en paper trading actif
- `paper_ready` — validée, prête pour paper (enabled: false)
- `paper_testing` — en test paper
- `stopped` — stoppée (kill switch ou manuel)

---

### Exécution

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `exec/killswitch.json` | KILL_SWITCH_GUARDIAN | POLICY_ENGINE, Dashboard | ✅ OUI — état kill switch |
| `exec/daily_pnl_testnet.json` | TESTNET_EXECUTOR | Dashboard | Dérivé (analytics) |

---

### Schedules agents

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `schedules/*.schedule.json` | Manuel (configuration) | poller.js | ✅ OUI — config schedules |

**⚠️ Important :** `agent_id` dans le schedule = nom exact du dossier dans `TRADING_FACTORY/`.
C'est le mapping utilisé par `poller.js` ligne 44 pour construire le chemin vers l'agent.
Un agent_id incorrect = agent introuvable = erreur silencieuse.

---

### Configs whale

| Fichier | Écrit par | Lu par | Rôle |
|---------|-----------|--------|------|
| `configs/WHALE_FEED.config.json` | Manuel | WHALE_FEED | Config sources et seuils |
| `configs/WHALE_ANALYZER.config.json` | Manuel | WHALE_ANALYZER | Config classification |
| `configs/exchange_addresses.json` | Manuel | WHALE_FEED, WHALE_ANALYZER | Adresses exchanges surveillées |

---

### Analytics et coûts LLM

| Fichier | Écrit par | Lu par | Nature |
|---------|-----------|--------|--------|
| `learning/token_costs.jsonl` | logTokens.js (tous agents LLM) | GLOBAL_TOKEN_TRACKER, Dashboard | ✅ Source brute |
| `learning/token_summary.json` | GLOBAL_TOKEN_TRACKER | Dashboard | Dérivé |
| `learning/token_recommendations.json` | GLOBAL_TOKEN_ANALYST | — | Dérivé |
| `learning/strategy_ranking.json` | PERFORMANCE_ANALYST | Dashboard, STRATEGY_SCOUT | Dérivé |
| `learning/strategy_performance.json` | PERFORMANCE_ANALYST | Dashboard | Dérivé |
| `learning/strategy_versions.json` | TRADE_STRATEGY_TUNER | TRADE_STRATEGY_TUNER | ✅ Source versionning |
| `learning/strategy_candidates.json` | TRADE_STRATEGY_TUNER | STRATEGY_GATEKEEPER | Dérivé |
| `learning/tuner_audit.jsonl` | TRADE_STRATEGY_TUNER | — | Audit append-only |
| `learning/global_performance.json` | PERFORMANCE_ANALYST | Dashboard | Dérivé |
| `learning/asset_performance.json` | PERFORMANCE_ANALYST | Dashboard | Dérivé |
| `learning/regime_performance_matrix.json` | PERFORMANCE_ANALYST | Dashboard | Dérivé |
| `learning/daily_performance.json` | PERFORMANCE_ANALYST | Dashboard | Dérivé |

**⚠️ Les fichiers `learning/*.json` sauf `token_costs.jsonl` sont des dérivés.**
Ne pas les utiliser comme source de vérité principale — toujours remonter
aux wallets et positions.

---

### Bus events — topics et TTL

| Topic | Fichier JSONL | Producteur | Consommateur | TTL |
|-------|--------------|------------|--------------|-----|
| `trading.raw.market.ticker` | `bus/trading_raw_market_ticker.jsonl` | BINANCE_PRICE_FEED | MARKET_EYE | 1 jour |
| `trading.intel.market.features` | `bus/trading_intel_market_features.jsonl` | MARKET_EYE | REGIME_DETECTOR, TRADE_GENERATOR, PREDICTOR | 2 jours |
| `trading.raw.news.article` | `bus/trading_raw_news_article.jsonl` | NEWS_FEED | NEWS_SCORING | Variable |
| `trading.intel.news.event` | `bus/trading_intel_news_event.jsonl` | NEWS_SCORING | TRADE_GENERATOR | Variable |
| `trading.raw.whale.transfer` | `bus/trading_raw_whale_transfer.jsonl` | WHALE_FEED | WHALE_ANALYZER | 2 jours |
| `trading.intel.whale.signal` | `bus/trading_intel_whale_signal.jsonl` | WHALE_ANALYZER | REGIME_DETECTOR | 7 jours |
| `trading.intel.regime` | `bus/trading_intel_regime.jsonl` | REGIME_DETECTOR | TRADE_GENERATOR | 90 jours |
| `trading.intel.prediction` | `bus/trading_intel_prediction.jsonl` | PREDICTOR | ⚠️ inconnu | 7 jours |
| `trading.strategy.trade.proposal` | `bus/trading_strategy_trade_proposal.jsonl` | TRADE_GENERATOR | RISK_MANAGER | 90 jours |
| `trading.strategy.order.plan` | `bus/trading_strategy_order_plan.jsonl` | RISK_MANAGER | POLICY_ENGINE, TRADING_ORCHESTRATOR | Variable |
| `trading.strategy.policy.decision` | `bus/trading_strategy_policy_decision.jsonl` | POLICY_ENGINE | TRADING_ORCHESTRATOR | Variable |
| `trading.exec.order.submit` | `bus/trading_exec_order_submit.jsonl` | TRADING_ORCHESTRATOR | TESTNET/PAPER_EXECUTOR | Variable |
| `trading.exec.position.snapshot` | `bus/trading_exec_position_snapshot.jsonl` | Executors | Dashboard | 30 jours |
| `trading.exec.trade.ledger` | `bus/trading_exec_trade_ledger.jsonl` | Executors | PERFORMANCE_ANALYST | 365 jours |
| `trading.ops.killswitch.state` | `bus/trading_ops_killswitch_state.jsonl` | KILL_SWITCH_GUARDIAN | POLICY_ENGINE, Dashboard | Variable |

**⚠️ Topics bus = string constants dans le code, pas des chemins filesystem.**
Déplacer `TRADING_FACTORY/` n'affecte pas les topics.

**Rotation gérée par :**
- `TRADING_FACTORY/bus_rotation.js` (cron `0 3 * * *`)
- `TRADING_FACTORY/bus_cleanup_trading.js` (cron `30 3 * * *` + `0 2 * * dim`)

---

### État runtime agents

| Fichier | Écrit par | Lu par | Rôle |
|---------|-----------|--------|------|
| `memory/*.state.json` | agentRuntime.js | SYSTEM_WATCHDOG, Dashboard | État et curseur bus de chaque agent |

Un fichier par agent actif. Contient le curseur bus (dernière position lue)
et l'état interne de l'agent. Utilisé pour la détection STALE par le dashboard.

---

### Audit (jamais purgé)

| Fichier | Rôle |
|---------|------|
| `audit/*.jsonl` | Copie append-only de toutes les décisions critiques |

**Ne jamais purger ni modifier ces fichiers.**

---

## HIÉRARCHIE DES SOURCES — TRADING

Pour une même métrique, priorité décroissante :

1. `strategies/*/wallet.json` → capital, cash, PnL réalisé par stratégie
2. `exec/positions_testnet.json` → positions ouvertes
3. `exec/killswitch.json` → état kill switch
4. `learning/strategy_ranking.json` → ranking (dérivé PERFORMANCE_ANALYST)
5. `bus/*.jsonl` → historique events (append-only, immuable)
6. `memory/*.state.json` → état runtime agents
7. `poller.log` → debug uniquement, jamais source de vérité

---

## TAILLES ET RÉTENTION BUS

| Topic | TTL | Taille typique |
|-------|-----|----------------|
| `market_features` | 2 jours | ~20 MB (5m) |
| `raw_market_ticker` | 1 jour | ~12 MB |
| `intel_prediction` | 7 jours | ~10 MB |
| `raw_whale_transfer` | 2 jours | ~1 MB |
| `intel_whale_signal` | 7 jours | ~500 KB |
| `exec_position_snapshot` | 30 jours | ~5 MB |
| `intel_regime` | 90 jours | ~4 MB |
| `strategy_trade_proposal` | 90 jours | ~3 MB |
| `exec_trade_ledger` | 365 jours | ~8 KB (peu de trades) |
| `audit/*` | Jamais | Croissance continue |
