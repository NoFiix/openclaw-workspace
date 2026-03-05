# CryptoRizon — Trading Agents Architecture
**Version** : 1.1.0  
**Date** : Mars 2026  
**Statut** : ✅ Conception fermée — prêt pour Sprint 1  

---

## Table des matières

1. [Vision et principes](#1-vision-et-principes)
2. [Vue globale du système](#2-vue-globale-du-système)
3. [Infrastructure Docker](#3-infrastructure-docker)
4. [Event Bus — topics et envelope](#4-event-bus--topics-et-envelope)
5. [Couche 0 — Data & Ops](#5-couche-0--data--ops)
6. [Couche 1 — Intelligence](#6-couche-1--intelligence)
7. [Couche 2 — Stratégie](#7-couche-2--stratégie)
8. [Couche 3 — Exécution](#8-couche-3--exécution)
9. [Couche 4 — Optimisation](#9-couche-4--optimisation)
10. [Sources de données et coûts](#10-sources-de-données-et-coûts)
11. [Règles anchor.md trading](#11-règles-anchormd-trading)
12. [Roadmap par sprints](#12-roadmap-par-sprints)
13. [Estimation des coûts tokens](#13-estimation-des-coûts-tokens)

---

## 1. Vision et principes

**Objectif** : Système d'agents IA autonomes capables de détecter des opportunités de trading crypto, d'exécuter des transactions et d'améliorer leurs performances en continu — avec supervision humaine sur les décisions critiques.

**Principes non négociables** :

- **Pipeline strict** : tout trade passe par `TRADE_GENERATOR → RISK_MANAGER → POLICY_GATEKEEPER → TRADING_VALIDATOR → TRADER`. Aucun shortcut.
- **Paper trading obligatoire** : 30 jours minimum avant tout trade live sur chaque nouvelle stratégie.
- **Kill switch automatique** : arrêt immédiat si pertes > 3% en 24h ou anomalie système détectée.
- **Approbation humaine** : tout order plan au-dessus du seuil configuré attend un ACK Telegram avant exécution.
- **Isolation totale** : le `trading-poller` est un service Docker séparé du `content-poller`. Aucune dépendance runtime entre les deux.
- **Auditabilité complète** : chaque décision est tracée sur `trading.audit.*`, jamais purgée automatiquement.

**Phase actuelle** : CEX only (Binance). DEX reporté en Phase 4.

---

## 2. Vue globale du système

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TRADING_VALIDATOR                                 │
│   Vérifie : killswitch.state + human.approval avant tout exec.order.submit  │
│   Alerte : Telegram "Trader - Agents"                                       │
└─────────────────────────────────────────────────────────────────────────────┘
           │                      │                        │
           ▼                      ▼                        ▼
┌─────────────────┐   ┌────────────────────┐   ┌──────────────────────┐
│   COUCHE 0      │   │    COUCHE 2         │   │     COUCHE 3         │
│   DATA & OPS    │   │    STRATÉGIE        │   │     EXÉCUTION        │
│                 │   │                    │   │                      │
│ BINANCE_PRICE_FEED    │   │ TRADE_GENERATOR   │   │ TRADER             │
│ NEWS_FEED       │   │  confirmation      │   │  + idempotence       │
│ DATA_QUALITY    │   │  adaptative        │   │ ORDER_RECONCILER     │
│ KILL_SWITCH     │   │ RISK_MANAGER       │   │ POSITION_MANAGER     │
│                 │   │ POLICY_GATEKEEPER      │   │ TRADE_LOG            │
│ (GAS_MANAGER    │   │  + cooldown        │   └──────────────────────┘
│  → _deferred/   │   │  + human approval  │              │
│  Phase 4 DEX)   │   │ PORTFOLIO_MANAGER  │              ▼
└─────────────────┘   └────────────────────┘   ┌──────────────────────┐
           │                      │             │     COUCHE 4         │
           ▼                      │             │     OPTIMISATION     │
┌─────────────────┐               │             │                      │
│   COUCHE 1      │               │             │ PERFORMANCE_ANALYST  │
│   INTELLIGENCE  │               │             │ STRATEGY_TUNER       │
│                 │               │             │ LEARNER              │
│ MARKET_EYE      │               │             │  (voit les blocks)   │
│ NEWS_SCORING  │               │             │ DARWIN_SELECTOR   │
│ SENTIMENT       │               │             └──────────────────────┘
│ ONCHAIN_ANALYST │               │
│ WHALE_WATCHER   │               │
│ REGIME_DETECTOR │               │
│  (+ news input) │               │
│ PREDICTOR v1    │               │
│  (stats pures)  │               │
└─────────────────┘               │
           └──────────────────────┘
                  EVENT BUS (JSONL file-based)
```

---

## 3. Infrastructure Docker

### Services docker-compose

```yaml
services:

  openclaw-gateway:
    image: ghcr.io/openclaw/openclaw:2026.3.2
    # Orchestration générale — inchangé
    restart: unless-stopped

  trading-poller:
    build: ./trading-poller
    restart: always
    cpu_shares: 2048          # Priorité haute
    mem_limit: 512m
    environment:
      - TRADING_ENV=paper
      - EVENTBUS_BACKEND=file
      - STATE_DIR=/workspace/state/trading
      - WORKSPACE_DIR=/workspace
    volumes:
      - ./workspace:/workspace
    healthcheck:
      test: ["CMD", "node", "healthcheck.js"]
      interval: 30s
      timeout: 5s
      retries: 3
    depends_on: []             # Aucune dépendance sur content-poller

  content-poller:
    build: ./content-poller
    restart: unless-stopped
    cpu_shares: 512            # Priorité basse
    mem_limit: 1g
    environment:
      - WORKSPACE_DIR=/workspace
    volumes:
      - ./workspace:/workspace
```

### Variables `.env` (Sprint 1)

```bash
# --- Existant (inchangé) ---
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
TELEGRAM_BOT_TOKEN=...           # Publisher bot CryptoRizon
TELEGRAM_CHAT_ID=...             # Channel CryptoRizon public
TWITTER_API_KEY=...
TWITTER_API_SECRET=...
TWITTER_ACCESS_TOKEN=...
TWITTER_ACCESS_TOKEN_SECRET=...

# --- Nouveaux Sprint 1 ---
TRADER_TELEGRAM_BOT_TOKEN=...    # Bot "Trader - Agents" (nouveau BotFather)
TRADER_TELEGRAM_CHAT_ID=...      # Channel privé "Trader - Agents"
BINANCE_API_KEY=...              # Read-only + pas de withdraw
BINANCE_API_SECRET=...

# --- Config trading ---
TRADING_ENV=paper                # paper | live — verrouillé paper 30 jours min
EVENTBUS_BACKEND=file            # file | redis
TRADING_MAX_HOT_WALLET_USD=0     # Phase 1 : pas de wallet actif

# --- Phase 4 DEX (pas encore actifs) ---
# HOT_WALLET_PRIVATE_KEY=...
# RPC_BASE=...
# RPC_ARBITRUM=...
```

### Structure workspace

```
workspace/
├── skills_custom/
│   └── trading/
│       ├── _shared/
│       │   └── agentRuntime.js
│       ├── _deferred/           ← agents DEX Phase 4
│       │   ├── GAS_MANAGER/
│       │   └── FEED_DEX/
│       ├── BINANCE_PRICE_FEED/
│       │   ├── skill.json
│       │   ├── index.js
│       │   └── handler.js
│       ├── MARKET_EYE/
│       ├── NEWS_FEED/
│       ├── NEWS_SCORING/
│       ├── PREDICTOR/
│       ├── REGIME_DETECTOR/
│       ├── SENTIMENT_ANALYST/
│       ├── ONCHAIN_ANALYST/
│       ├── WHALE_WATCHER/
│       ├── TRADE_GENERATOR/
│       ├── RISK_MANAGER/
│       ├── POSITION_SIZER/
│       ├── PORTFOLIO_MANAGER/
│       ├── CORRELATION_MANAGER/
│       ├── POLICY_GATEKEEPER/
│       ├── TRADING_VALIDATOR/
│       ├── TRADER/
│       ├── ORDER_RECONCILER/
│       ├── POSITION_MANAGER/
│       ├── TRADE_LOG/
│       ├── PERFORMANCE_ANALYST/
│       ├── STRATEGY_TUNER/
│       ├── LEARNER/
│       └── DARWIN_SELECTOR/
│
└── state/
    └── trading/
        ├── bus/                 ← fichiers JSONL par topic
        ├── schedules/           ← 1 schedule JSON par agent
        ├── configs/             ← 1 config JSON par agent
        ├── memory/              ← 1 state JSON par agent (curseurs, cache)
        ├── exec/
        │   ├── pending_orders.json   ← registre idempotence TRADER
        │   └── cooldowns.json        ← cooldowns POLICY_GATEKEEPER
        ├── dead_letter/         ← erreurs non traitées
        └── audit/               ← append-only, jamais purgé automatiquement
```

---

## 4. Event Bus — topics et envelope

### Taxonomy des topics

```
RAW (ingestion brute, non interprétée)
  trading.raw.market.ticker
  trading.raw.market.ohlcv
  trading.raw.market.orderbook
  trading.raw.derivatives.funding
  trading.raw.derivatives.open_interest
  trading.raw.liquidations
  trading.raw.social.post               ← tweets/posts influenceurs (NEWS_FEED)
  trading.raw.social.metrics
  trading.raw.news.article
  trading.raw.onchain.metric
  trading.raw.whale.transfer

INTEL (normalisé, interprété)
  trading.intel.market.features
  trading.intel.sentiment.score
  trading.intel.news.event
  trading.intel.onchain.flows
  trading.intel.whale.alert
  trading.intel.regime
  trading.intel.prediction              ← PREDICTOR output

STRATEGY (raisonnement → propositions → plans)
  trading.strategy.trade.proposal
  trading.strategy.risk.review
  trading.strategy.portfolio.target
  trading.strategy.order.plan
  trading.strategy.block

EXEC (ordres, états, positions)
  trading.exec.order.submit
  trading.exec.order.ack
  trading.exec.order.fill
  trading.exec.order.cancel
  trading.exec.order.error
  trading.exec.position.snapshot
  trading.exec.trade.ledger

PERF (rapports, optimisation)
  trading.perf.daily.report
  trading.perf.weekly.report
  trading.perf.strategy.metrics
  trading.perf.tuning.suggestion
  trading.perf.learning.insight

OPS / AUDIT
  trading.ops.health.exchange
  trading.ops.health.data
  trading.ops.alert
  trading.ops.killswitch.state
  trading.ops.human.approval.request    ← POLICY_GATEKEEPER → attend ACK
  trading.ops.human.approval.ack        ← Bot Telegram → déblocage ORCHESTRATOR
  trading.ops.human.approval.timeout    ← ORCHESTRATOR → abort après 10 min
  trading.audit.event                   ← copie append-only de tout ce qui compte
  trading.audit.decision                ← décision finale + inputs hashés
```

### Event Envelope standard

Tous les messages utilisent ce wrapper sans exception.

```json
{
  "event_id": "uuid-v4",
  "ts": 1710000000000,
  "topic": "trading.intel.market.features",
  "type": "intel.market.features.v1",
  "producer": {
    "agent_id": "MARKET_EYE",
    "run_id": "uuid-v4",
    "version": "1.0.0"
  },
  "trace": {
    "trace_id": "uuid-v4",
    "correlation_id": "uuid-v4",
    "causation_id": "uuid-v4"
  },
  "scope": {
    "env": "paper",
    "chain": "none",
    "dex": "none",
    "exchange": "binance",
    "account": "main",
    "asset": "BTCUSDT",
    "timeframe": "1m"
  },
  "quality": {
    "score": 0.95,
    "flags": []
  },
  "privacy": {
    "contains_secrets": false,
    "redactions": []
  },
  "payload": {}
}
```

**Règles absolues sur l'envelope** :
- `payload` ne contient jamais de clés API, secrets, clés privées.
- `trace.*` est obligatoire dès qu'un event découle d'un autre.
- Tout ce qui touche à une décision (proposal / plan / submit / fill) est copié sur `trading.audit.*`.

---

## 5. Couche 0 — Data & Ops

### BINANCE_PRICE_FEED

```json
{
  "agent_id": "BINANCE_PRICE_FEED",
  "layer": "DATA",
  "llm": false,
  "consumes": [],
  "produces": [
    "trading.raw.market.ticker",
    "trading.raw.market.ohlcv",
    "trading.raw.derivatives.funding",
    "trading.raw.derivatives.open_interest",
    "trading.raw.liquidations"
  ],
  "schedule": { "mode": "daemon" },
  "note": "WebSocket Binance. Pas de LLM. Sources : Binance WS streams + REST OHLCV."
}
```

### NEWS_FEED

```json
{
  "agent_id": "NEWS_FEED",
  "layer": "DATA",
  "llm": false,
  "consumes": [],
  "produces": ["trading.raw.social.post", "trading.raw.news.article"],
  "schedule": { "mode": "daemon" },
  "sources": {
    "priority_1_telegram": {
      "library": "gramjs (MTProto)",
      "latency": "~30s",
      "channels": "proxy channels repostant Trump, Musk, SEC, CZ, Saylor"
    },
    "priority_2_nitter": {
      "instances": [
        "nitter.privacydev.net",
        "nitter.poast.org",
        "nitter.1d4.us"
      ],
      "latency": "60-120s",
      "fallback": "si Telegram KO depuis 5 min"
    },
    "priority_3_other": [
      "CryptoPanic API (free tier, 100 req/h)",
      "SEC EDGAR RSS atom",
      "Whale Alert API (free tier, seuil $500k)"
    ]
  },
  "watchlist_config": "state/trading/configs/NEWS_FEED.config.json",
  "dedup": "hash(handle + contenu) dans state",
  "fallback_alert": "Si Telegram ET Nitter KO → trading.ops.alert"
}
```

**Watchlist initiale** (`NEWS_FEED.config.json`) :
```json
{
  "twitter_watchlist": {
    "CRITICAL": [
      { "handle": "SECGov",         "keywords": [] },
      { "handle": "federalreserve", "keywords": [] },
      { "handle": "binance",        "keywords": ["listing", "delist"] },
      { "handle": "coinbase",       "keywords": ["listing", "delist"] }
    ],
    "MARKET_MOVERS": [
      { "handle": "realDonaldTrump", "keywords": ["bitcoin", "crypto", "tariff", "fed", "dollar"] },
      { "handle": "cz_binance",      "keywords": [] },
      { "handle": "saylor",          "keywords": [] }
    ],
    "NARRATIVE": [
      { "handle": "elonmusk", "keywords": ["bitcoin", "doge", "crypto", "x"] }
    ]
  },
  "noise_filter": "NARRATIVE sources ne déclenchent pas de fast_path. Signal uniquement si keywords match.",
  "nitter_instances": [
    "nitter.privacydev.net",
    "nitter.poast.org",
    "nitter.1d4.us",
    "nitter.tiekoetter.com",
    "nitter.nl"
  ]
}
```

### DATA_QUALITY

```json
{
  "agent_id": "DATA_QUALITY",
  "layer": "DATA",
  "llm": false,
  "consumes": ["trading.raw.market.*", "trading.raw.news.article", "trading.raw.whale.transfer"],
  "produces": ["trading.ops.health.data", "trading.audit.event"],
  "schedule": { "mode": "poll", "every_seconds": 15 },
  "payload_schema": {
    "source": "binance|news|onchain",
    "status": "OK|DEGRADED|DOWN",
    "issues": [{ "code": "GAP|STALE|DUPLICATE|SPIKE", "details": "" }]
  }
}
```

### KILL_SWITCH_GUARDIAN

```json
{
  "agent_id": "KILL_SWITCH_GUARDIAN",
  "layer": "OPS",
  "llm": false,
  "consumes": [
    "trading.exec.order.error",
    "trading.ops.health.exchange",
    "trading.ops.health.data",
    "trading.perf.strategy.metrics"
  ],
  "produces": ["trading.ops.killswitch.state", "trading.ops.alert"],
  "schedule": { "mode": "poll", "every_seconds": 5 },
  "trip_conditions": [
    "Perte > 3% du capital total en 24h glissantes",
    "3+ erreurs TRADER consécutives sans fill confirmé",
    "Exchange health DOWN depuis > 5 minutes",
    "Data quality DEGRADED depuis > 15 minutes",
    "Gas cost > $1 par transaction (Phase 4 DEX uniquement)"
  ],
  "on_trip": [
    "Émettre killswitch.state = TRIPPED",
    "Alerte Telegram Trader-Agents",
    "Ne PAS annuler les ordres ouverts (alerte humaine uniquement)",
    "Reprendre nécessite un reset manuel du state"
  ],
  "telegram_channel": "TRADER_TELEGRAM_CHAT_ID"
}
```

---

## 6. Couche 1 — Intelligence

### MARKET_EYE

```json
{
  "agent_id": "MARKET_EYE",
  "layer": "INTELLIGENCE",
  "llm": false,
  "consumes": [
    "trading.raw.market.ticker",
    "trading.raw.market.ohlcv",
    "trading.raw.derivatives.funding",
    "trading.raw.derivatives.open_interest",
    "trading.raw.liquidations"
  ],
  "produces": ["trading.intel.market.features"],
  "schedule": { "mode": "poll", "every_seconds": 10 },
  "payload_schema": {
    "price": 0,
    "returns": { "1m": 0, "5m": 0, "1h": 0, "4h": 0, "1D": 0 },
    "volatility": { "5m": 0, "1h": 0, "4h": 0 },
    "volume": { "zscore_1h": 0, "spike_ratio": 0 },
    "indicators": {
      "rsi_14": 0,
      "bb_upper": 0, "bb_lower": 0, "bb_mid": 0,
      "macd": 0, "macd_signal": 0,
      "atr_14": 0
    },
    "orderbook": { "spread_bps": 0, "imbalance": 0 },
    "derivatives": { "funding": 0, "oi_change": 0 },
    "liquidations": { "notional_5m": 0 },
    "timeframe_features": {
      "1h": { "rsi": 0, "trend": "up|down|range" },
      "4h": { "rsi": 0, "trend": "up|down|range" },
      "1D": { "rsi": 0, "trend": "up|down|range" }
    }
  },
  "note": "Produit des features par timeframe. Input principal du PREDICTOR."
}
```

### PREDICTOR (Niveau A — statistique pure)

```json
{
  "agent_id": "PREDICTOR",
  "layer": "INTELLIGENCE",
  "llm": false,
  "version": "A",
  "position_in_flow": "Entre REGIME_DETECTOR et TRADE_GENERATOR",
  "consumes": [
    "trading.intel.market.features",
    "trading.intel.regime"
  ],
  "produces": ["trading.intel.prediction"],
  "schedule": { "mode": "poll", "every_seconds": 60 },
  "scoring_logic": {
    "weighted_signals": {
      "RSI_oversold_overbought": 0.5,
      "bollinger_band_touch":    0.5,
      "volume_spike":            1.0,
      "macd_cross":              1.0,
      "regime_confirmation":     1.0
    },
    "rationale": "RSI et BB seuls sont faibles (0.5 chacun). MACD + volume spike = signaux forts (1.0). Regime confirm = boost décisif.",
    "bullish_conditions": [
      "RSI < 30 → +0.5",
      "Prix < BB_lower (2σ) → +0.5",
      "Volume z-score > 2 + prix hausse → +1.0",
      "MACD cross bullish → +1.0",
      "Regime = TREND up confirmé → +1.0"
    ],
    "bearish_conditions": [
      "RSI > 70 → +0.5",
      "Prix > BB_upper (2σ) → +0.5",
      "Volume z-score > 2 + prix baisse → +1.0",
      "MACD cross bearish → +1.0",
      "Regime = PANIC ou TREND down confirmé → +1.0"
    ],
    "direction_prob": "score_bullish / (score_bullish + score_bearish)",
    "confidence": "max_score_side / 4.0"
  },
  "payload_schema": {
    "asset": "BTCUSDT",
    "direction_prob": 0.65,
    "confidence": 0.75,
    "model_type": "statistical_v1",
    "signals_used": ["rsi_28", "bb_lower", "volume_zscore_2"],
    "horizon": "1h",
    "regime_context": "RANGE"
  },
  "phase_3_upgrade": "Niveau B — scikit-learn Python, gradient boosting, entraînement hebdo"
}
```

### REGIME_DETECTOR

```json
{
  "agent_id": "REGIME_DETECTOR",
  "layer": "INTELLIGENCE",
  "llm": false,
  "consumes": [
    "trading.intel.market.features",
    "trading.intel.news.event"
  ],
  "produces": ["trading.intel.regime"],
  "schedule": { "mode": "poll", "every_seconds": 300 },
  "payload_schema": {
    "regime": "RANGE|TREND|PANIC|NEWS_DRIVEN|EUPHORIA",
    "confidence": 0.8,
    "explain": ["high_volatility", "news_spike"],
    "news_trigger": "event_id_si_NEWS_DRIVEN_sinon_null"
  }
}
```

### NEWS_SCORING

```json
{
  "agent_id": "NEWS_SCORING",
  "layer": "INTELLIGENCE",
  "llm": true,
  "model": "haiku",
  "consumes": ["trading.raw.news.article", "trading.raw.social.post"],
  "produces": ["trading.intel.news.event"],
  "schedule": { "mode": "poll", "every_seconds": 60 },
  "fast_path": "Si social.post.priority = CRITICAL → traitement immédiat (bypass schedule)",
  "payload_schema": {
    "headline": "",
    "category": "REGULATION|HACK|LISTING|ETF|MACRO|PARTNERSHIP|SOCIAL_INFLUENCER",
    "urgency": 0,
    "reliability": { "score": 0, "confirmed_by": 0 },
    "entities": ["BTC", "SEC"],
    "summary": "",
    "source_refs": [{ "name": "", "url": "" }]
  }
}
```

### SENTIMENT_ANALYST

```json
{
  "agent_id": "SENTIMENT_ANALYST",
  "layer": "INTELLIGENCE",
  "llm": true,
  "model": "haiku",
  "consumes": ["trading.raw.social.post", "trading.raw.social.metrics"],
  "produces": ["trading.intel.sentiment.score"],
  "schedule": { "mode": "poll", "every_seconds": 900 },
  "payload_schema": {
    "score": 0,
    "confidence": 0,
    "drivers": ["FUD", "FOMO", "ETF", "REGULATION", "HACK"],
    "top_entities": ["BTC", "ETH"],
    "sample_size": 0
  }
}
```

### ONCHAIN_ANALYST

```json
{
  "agent_id": "ONCHAIN_ANALYST",
  "layer": "INTELLIGENCE",
  "llm": false,
  "consumes": ["trading.raw.onchain.metric"],
  "produces": ["trading.intel.onchain.flows"],
  "schedule": { "mode": "poll", "every_seconds": 3600 },
  "sources": ["Glassnode free tier", "DefiLlama API", "Whale Alert free tier"],
  "payload_schema": {
    "exchange_netflow": 0,
    "stablecoin_flows": { "to_exchanges": 0, "from_exchanges": 0 },
    "tvl_change_24h": 0,
    "notes": []
  }
}
```

### WHALE_WATCHER

```json
{
  "agent_id": "WHALE_WATCHER",
  "layer": "INTELLIGENCE",
  "llm": false,
  "consumes": ["trading.raw.whale.transfer"],
  "produces": ["trading.intel.whale.alert"],
  "schedule": { "mode": "poll", "every_seconds": 60 },
  "payload_schema": {
    "direction": "TO_EXCHANGE|FROM_EXCHANGE|UNKNOWN",
    "notional_usd": 0,
    "label": "institution|unknown|cex",
    "severity": 0,
    "tx_ref": ""
  }
}
```

---

## 7. Couche 2 — Stratégie

### TRADE_GENERATOR

```json
{
  "agent_id": "TRADE_GENERATOR",
  "layer": "STRATEGY",
  "llm": true,
  "model": "haiku (sonnet si confidence haute)",
  "consumes": [
    "trading.intel.market.features",
    "trading.intel.sentiment.score",
    "trading.intel.onchain.flows",
    "trading.intel.whale.alert",
    "trading.intel.news.event",
    "trading.intel.regime",
    "trading.intel.prediction"
  ],
  "produces": ["trading.strategy.trade.proposal"],
  "schedule": { "mode": "poll", "every_seconds": 60 },
  "confirmation_modes": {
    "NewsTrading":        "Aucune confirmation — urgency score suffit. Latence : secondes.",
    "SentimentExtremes":  "Fear & Greed + sentiment score concordants. Latence : minutes.",
    "WhaleFollowing":     "2 signaux whale concordants sur même asset. Latence : minutes.",
    "Momentum":           "Features 1h ET 4h alignées. Latence : heures.",
    "MeanReversion":      "RSI oversold/overbought + volume z-score. Latence : heures.",
    "SwingPosition":      "Features 4h ET 1D alignées. Latence : jours."
  },
  "payload_schema": {
    "strategy": "Momentum|MeanReversion|NewsTrading|WhaleFollowing|SentimentExtremes",
    "side": "BUY|SELL|HOLD",
    "confidence": 0.0,
    "confirmation_mode": "NewsTrading|Momentum|...",
    "setup": { "entry": 0, "stop": 0, "tp": 0 },
    "time_horizon": "minutes|hours|days",
    "reasons": [],
    "constraints": { "max_slippage_bps": 0, "cooldown_minutes": 30 }
  }
}
```

### RISK_MANAGER

```json
{
  "agent_id": "RISK_MANAGER",
  "layer": "STRATEGY",
  "llm": false,
  "consumes": [
    "trading.strategy.trade.proposal",
    "trading.exec.position.snapshot"
  ],
  "produces": ["trading.strategy.risk.review", "trading.strategy.block"],
  "schedule": { "mode": "event" },
  "rules": {
    "max_position_size_pct": 0.05,
    "max_trade_size_pct_capital": 0.02,
    "max_trade_size_pct_hot_wallet": 0.10,
    "max_daily_loss_pct": 0.03,
    "max_drawdown_pct": 0.15,
    "max_open_positions": 5,
    "max_correlated_positions": 2,
    "correlation_clusters": ["BTC/ETH/SOL/AVAX", "BNB/CAKE/ALPACA"],
    "correlation_limit": 0.30,
    "leverage_max": 1
  },
  "block_reasons": [
    "trade_size_exceeds_2pct_capital",
    "trade_size_exceeds_10pct_hot_wallet",
    "max_open_positions_reached",
    "max_correlated_positions_reached",
    "daily_loss_limit_reached",
    "max_drawdown_reached"
  ],
  "payload_schema": {
    "approved": true,
    "position_pct": 0,
    "max_loss_pct": 0,
    "leverage": 1,
    "notes": [],
    "limits": {
      "max_daily_loss": 0.03,
      "max_drawdown": 0.15,
      "max_trade_pct_capital": 0.02,
      "max_trade_pct_hot_wallet": 0.10,
      "max_open_positions": 5
    }
  }
}
```

### POLICY_GATEKEEPER

```json
{
  "agent_id": "POLICY_GATEKEEPER",
  "layer": "STRATEGY",
  "llm": false,
  "consumes": [
    "trading.strategy.trade.proposal",
    "trading.strategy.risk.review",
    "trading.ops.killswitch.state",
    "trading.ops.health.data"
  ],
  "produces": [
    "trading.strategy.order.plan",
    "trading.strategy.block",
    "trading.ops.human.approval.request",
    "trading.audit.decision"
  ],
  "schedule": { "mode": "event" },
  "cooldown_state": "state/trading/exec/cooldowns.json",
  "cooldown_logic": "Vérifier (now - last_trade_ts) < cooldown_minutes * 60. Si cooldown actif → émettre strategy.block reason=cooldown_active.",
  "slippage_guard": {
    "max_slippage_bps": 30,
    "logic": "Si slippage estimé > 30bps (0.3%) → émettre strategy.block reason=slippage_too_high. Essentiel sur small caps et pools peu liquides."
  },
  "volatility_circuit_breaker": {
    "trigger": "Si volatility_1m > 3 * ATR_14 → pause trading 10 minutes",
    "use_cases": ["cascade de liquidations", "hack/exploit annonce", "macro shock"],
    "state_file": "state/trading/exec/circuit_breaker.json",
    "logic": "Les signaux deviennent inutilisables en volatilité extrême. 10 min de pause protège contre les faux signaux en période chaotique."
  },
  "approval_threshold_usd": 100,
  "payload_schema": {
    "orders": [
      { "kind": "LIMIT|MARKET", "qty": 0, "price": 0, "time_in_force": "GTC" },
      { "kind": "STOP_LOSS", "qty": 0, "stop": 0 },
      { "kind": "TAKE_PROFIT", "qty": 0, "price": 0 }
    ],
    "approval": { "required": false, "threshold_usd": 100 },
    "risk": { "position_pct": 0, "max_slippage_bps": 0 }
  }
}
```

### TRADING_VALIDATOR

```json
{
  "agent_id": "TRADING_VALIDATOR",
  "layer": "ORCHESTRATION",
  "llm": false,
  "consumes": [
    "trading.strategy.order.plan",
    "trading.strategy.block",
    "trading.ops.killswitch.state",
    "trading.ops.human.approval.ack"
  ],
  "produces": [
    "trading.exec.order.submit",
    "trading.ops.human.approval.request",
    "trading.ops.human.approval.timeout",
    "trading.ops.alert"
  ],
  "schedule": { "mode": "event" },
  "safety_checks": [
    "1. Vérifier killswitch.state → si TRIPPED : émettre ops.alert, STOP.",
    "2. Si plan.approval.required = true → émettre ops.human.approval.request + attendre ACK.",
    "3. Timeout 10 min sans ACK → émettre ops.human.approval.timeout + ABORT.",
    "4. ACK reçu OU approval non requise → émettre exec.order.submit."
  ],
  "telegram_flow": "Boutons inline ✅ VALIDER / ❌ ANNULER dans Trader-Agents. Callback → ops.human.approval.ack.",
  "telegram_channel": "TRADER_TELEGRAM_CHAT_ID"
}
```

### PORTFOLIO_MANAGER

```json
{
  "agent_id": "PORTFOLIO_MANAGER",
  "layer": "STRATEGY",
  "llm": false,
  "consumes": [
    "trading.exec.position.snapshot",
    "trading.perf.strategy.metrics"
  ],
  "produces": ["trading.strategy.portfolio.target"],
  "schedule": { "mode": "poll", "every_seconds": 86400 },
  "allocation": {
    "core_pct": 0.60,
    "tactical_pct": 0.30,
    "degen_pct": 0.10,
    "cash_reserve_pct": 0.20
  }
}
```

### POSITION_SIZER

```json
{
  "agent_id": "POSITION_SIZER",
  "layer": "STRATEGY",
  "llm": false,
  "consumes": [
    "trading.strategy.trade.proposal",
    "trading.exec.position.snapshot",
    "trading.intel.market.features"
  ],
  "produces": ["trading.strategy.sized.proposal"],
  "schedule": { "mode": "event" },
  "formula": "size = (capital * risk_per_trade_pct) / stop_distance_pct",
  "caps": [
    "size <= 2% du capital total",
    "size <= 10% du hot wallet",
    "size <= max_position_size configuré dans RISK_MANAGER"
  ],
  "note": "Évite le bug classique : un signal sans sizing → 100% du capital engagé. POSITION_SIZER calcule la taille optimale selon le stop-loss et le risk-per-trade défini.",
  "payload_schema": {
    "original_proposal_ref": "event_id",
    "recommended_qty": 0,
    "risk_per_trade_pct": 0.01,
    "stop_distance_pct": 0,
    "notional_usd": 0,
    "cap_applied": "capital_2pct|hot_wallet_10pct|max_position|none"
  }
}
```

### CORRELATION_MANAGER

```json
{
  "agent_id": "CORRELATION_MANAGER",
  "layer": "STRATEGY",
  "llm": false,
  "consumes": [
    "trading.exec.position.snapshot",
    "trading.strategy.trade.proposal"
  ],
  "produces": ["trading.intel.correlation.alert", "trading.strategy.block"],
  "schedule": { "mode": "poll", "every_seconds": 60 },
  "clusters": {
    "btc_cluster": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT"],
    "bnb_cluster": ["BNBUSDT", "CAKEUSDT"],
    "note": "Configurable dans state/trading/configs/CORRELATION_MANAGER.config.json"
  },
  "rules": [
    "Maximum 2 positions ouvertes dans le même cluster",
    "Si nouvelle proposal concerne un asset dans un cluster déjà saturé → BLOCK"
  ],
  "rolling_window_days": 30,
  "payload_schema": {
    "current_exposure_by_cluster": {
      "btc_cluster": { "open_positions": 0, "total_notional_usd": 0 }
    },
    "alert": "cluster_saturated|high_correlation_detected|ok"
  }
}
```

### EXCHANGE_HEALTH

```json
{
  "agent_id": "EXCHANGE_HEALTH",
  "layer": "OPS",
  "llm": false,
  "consumes": [],
  "produces": ["trading.ops.health.exchange", "trading.ops.alert"],
  "schedule": { "mode": "poll", "every_seconds": 30 },
  "checks": [
    "Latence REST Binance (ping endpoint)",
    "Statut WebSocket BINANCE_PRICE_FEED (dernière donnée reçue < 60s)",
    "Orderbook freeze (dernier update > 30s sans changement)",
    "API rate limit restant (X-MBX-USED-WEIGHT header)"
  ],
  "fallback": "Si Binance DOWN → alerte Telegram + envisager bascule Bybit (Phase 2)",
  "payload_schema": {
    "exchange": "binance",
    "status": "OK|DEGRADED|DOWN",
    "latency_ms": 0,
    "ws_last_update_age_s": 0,
    "rate_limit_used_pct": 0,
    "issues": []
  }
}
```

---

## 8. Couche 3 — Exécution

### TRADER

```json
{
  "agent_id": "TRADER",
  "layer": "EXECUTION",
  "llm": false,
  "consumes": ["trading.exec.order.submit"],
  "produces": ["trading.exec.order.ack", "trading.exec.order.error"],
  "schedule": { "mode": "event" },
  "idempotence": {
    "state_file": "state/trading/exec/pending_orders.json",
    "logic": "Avant envoi : vérifier si idempotency_key existe avec status=SENT. Si oui : skip + log WARNING. Si non : écrire PENDING, envoyer, mettre à jour SENT."
  },
  "rate_guard": "Token bucket 1200 weight/min (Binance REST). Shared avec ORDER_RECONCILER.",
  "dry_run": "Si TRADING_ENV=paper : logger l'ordre sans l'envoyer. Émettre ack simulé.",
  "payload_schema": {
    "exchange_order_id": "",
    "status": "ACKED",
    "client_order_id": ""
  }
}
```

### ORDER_RECONCILER

```json
{
  "agent_id": "ORDER_RECONCILER",
  "layer": "EXECUTION",
  "llm": false,
  "consumes": ["trading.exec.order.ack"],
  "produces": ["trading.exec.order.fill", "trading.exec.order.cancel", "trading.exec.order.error"],
  "schedule": { "mode": "poll", "every_seconds": 10 },
  "payload_schema": {
    "exchange_order_id": "",
    "filled_qty": 0,
    "avg_price": 0,
    "fee": { "asset": "USDT", "amount": 0 },
    "status": "PARTIAL|FILLED"
  }
}
```

### POSITION_MANAGER

```json
{
  "agent_id": "POSITION_MANAGER",
  "layer": "EXECUTION",
  "llm": false,
  "consumes": ["trading.exec.order.fill", "trading.exec.order.cancel"],
  "produces": ["trading.exec.position.snapshot"],
  "schedule": { "mode": "poll", "every_seconds": 15 },
  "payload_schema": {
    "positions": [
      { "asset": "BTCUSDT", "qty": 0, "entry": 0, "mark": 0, "uPnL": 0, "rPnL": 0 }
    ],
    "equity": 0,
    "available_cash": 0
  }
}
```

### TRADE_LOG

```json
{
  "agent_id": "TRADE_LOG",
  "layer": "EXECUTION",
  "llm": false,
  "consumes": ["trading.exec.order.fill"],
  "produces": ["trading.exec.trade.ledger", "trading.audit.event"],
  "schedule": { "mode": "event" },
  "payload_schema": {
    "trade_id": "uuid",
    "exchange": "binance",
    "asset": "BTCUSDT",
    "side": "BUY",
    "qty": 0,
    "price": 0,
    "fee_usd": 0,
    "slippage_bps": 0,
    "links": {
      "proposal_event_id": "",
      "plan_event_id": ""
    }
  }
}
```

---

## 9. Couche 4 — Optimisation

### PERFORMANCE_ANALYST

```json
{
  "agent_id": "PERFORMANCE_ANALYST",
  "layer": "OPTIMIZATION",
  "llm": true,
  "model": "haiku",
  "consumes": ["trading.exec.trade.ledger", "trading.exec.position.snapshot"],
  "produces": ["trading.perf.strategy.metrics", "trading.perf.daily.report"],
  "schedule": { "mode": "poll", "every_seconds": 86400 },
  "telegram_report": "Rapport daily/weekly automatique → Trader-Agents",
  "payload_schema": {
    "window": "1d|7d|30d",
    "win_rate": 0,
    "profit_factor": 0,
    "max_drawdown": 0,
    "sharpe": 0,
    "net_pnl": 0,
    "benchmarks": { "hold_btc": 0, "dca": 0 }
  }
}
```

### LEARNER

```json
{
  "agent_id": "LEARNER",
  "layer": "OPTIMIZATION",
  "llm": true,
  "model": "haiku",
  "consumes": [
    "trading.exec.trade.ledger",
    "trading.perf.strategy.metrics",
    "trading.strategy.block"
  ],
  "produces": ["trading.perf.learning.insight"],
  "schedule": { "mode": "poll", "every_seconds": 86400 },
  "payload_schema": {
    "insights": [
      {
        "pattern": "news_false_positive",
        "evidence": ["event_id1"],
        "action": "raise_reliability_threshold"
      }
    ],
    "missed_opportunities": [
      {
        "block_reason": "risk_limit|cooldown|killswitch",
        "proposal_event_id": "",
        "retrospective_pnl": 0,
        "lesson": ""
      }
    ]
  }
}
```

### STRATEGY_TUNER

```json
{
  "agent_id": "STRATEGY_TUNER",
  "layer": "OPTIMIZATION",
  "llm": true,
  "model": "sonnet",
  "consumes": ["trading.perf.strategy.metrics"],
  "produces": ["trading.perf.tuning.suggestion"],
  "schedule": { "mode": "poll", "every_seconds": 604800 },
  "payload_schema": {
    "strategy": "",
    "changes": [{ "param": "rsi_threshold", "from": 25, "to": 28 }],
    "expected_effect": "reduce_false_signals",
    "safety": { "requires_paper_retest": true }
  }
}
```

### DARWIN_SELECTOR

```json
{
  "agent_id": "DARWIN_SELECTOR",
  "layer": "OPTIMIZATION",
  "llm": false,
  "consumes": ["trading.perf.strategy.metrics"],
  "produces": ["trading.strategy.portfolio.target"],
  "schedule": { "mode": "poll", "every_seconds": 604800 },
  "logic": "Chaque stratégie reçoit un budget virtuel. Hebdomadaire : les strats performantes reçoivent plus de capital (quota), les mauvaises en perdent. Après 3 mois : élimination des survivors négatifs.",
  "state_file": "state/trading/memory/DARWIN_SELECTOR.state.json"
}
```

---

## 10. Sources de données et coûts

| Source | Gratuit | Latence | Utilisation |
|--------|---------|---------|-------------|
| Binance WebSocket | ✅ | Real-time | BINANCE_PRICE_FEED |
| Binance REST | ✅ | < 1s | OHLCV, positions |
| Telegram MTProto (gramjs) | ✅ | ~30s | NEWS_FEED priority 1 |
| Nitter RSS (3 instances) | ✅ | 60-120s | NEWS_FEED fallback |
| CryptoPanic API free | ✅ | 1-2 min | NEWS_FEED |
| Fear & Greed Index (alternative.me) | ✅ | Daily | SENTIMENT |
| DefiLlama API | ✅ | 5-15 min | ONCHAIN |
| CoinGecko free (30 calls/min) | ✅ | 1 min | MARKET_EYE enrichment |
| Whale Alert free (10 req/min) | ✅ | Real-time | WHALE_WATCHER |
| Glassnode free tier | ✅ | 1h | ONCHAIN métriques basiques |
| SEC EDGAR RSS atom | ✅ | 5-10 min | NEWS_FEED |
| RSS crypto (scraper.js existant) | ✅ | 15-30 min | NEWS_FEED (réutilisé) |

**API Twitter payante** : reportée. À évaluer seulement si un edge prouvé en paper trading nécessite une latence < 30s sur les tweets influenceurs.

---

## 11. Règles anchor.md trading

Section à ajouter à `workspace/anchor.md` :

```markdown
## TRADING — Règles absolues (ne jamais déroger)

### Sécurité wallet et capital
- Ne JAMAIS stocker de clé privée wallet dans workspace/, state/, ni dans
  aucun fichier versionné Git. La clé privée hot wallet vit uniquement dans
  .env (non versionné, non committé).
- Le hot wallet de trading ne contient JAMAIS plus de TRADING_MAX_HOT_WALLET_USD€
  défini dans .env. Tout excédent est transféré vers cold wallet manuellement.
- Les token approvals (Phase 4 DEX) sont limités au montant exact du trade —
  jamais unlimited approve.

### Limites de taille par trade
- Aucun trade ne peut dépasser 2% du capital total.
- Aucun trade ne peut dépasser 10% du hot wallet.
- Si POLICY_GATEKEEPER reçoit un OrderPlan dépassant ces limites → BLOCK automatique.
- Sans cette règle, un bug peut envoyer 100% du capital en un trade.

### Limite de positions simultanées
- Maximum 5 positions ouvertes simultanément (toutes stratégies confondues).
- Maximum 2 positions corrélées dans le même cluster (BTC/ETH/SOL/AVAX).
- CORRELATION_MANAGER émet strategy.block si ces limites sont atteintes.
- Raison : sans cette règle, le bot peut ouvrir 12 trades corrélés → BTC dump → catastrophe.

### Slippage guard
- POLICY_GATEKEEPER refuse tout ordre si slippage estimé > 0.3% (30 bps).
- Particulièrement critique sur les small caps et paires peu liquides.
- Configurable dans POLICY_GATEKEEPER.config.json : slippage_guard.max_slippage_bps.

### Volatility circuit breaker
- Si volatilité 1m > 3 * ATR_14 → POLICY_GATEKEEPER suspend le trading 10 minutes.
- Les signaux deviennent inutilisables pendant les cascades de liquidation,
  hacks, et macro shocks. La pause protège contre les faux signaux en période chaotique.
- État stocké dans state/trading/exec/circuit_breaker.json.

### Pipeline obligatoire — aucun shortcut
- TOUT trade passe par le pipeline complet :
  TRADE_GENERATOR → POSITION_SIZER → RISK_MANAGER → CORRELATION_MANAGER
  → POLICY_GATEKEEPER → TRADING_VALIDATOR → TRADER
- Aucun agent ne peut appeler TRADER directement sans passer par POLICY_GATEKEEPER.
- POLICY_GATEKEEPER est l'unique porte d'émission d'OrderPlan. Règle d'architecture,
  pas une recommandation.

### Kill switch — conditions d'arrêt automatique
- KILL_SWITCH_GUARDIAN passe en TRIPPED si l'une de ces conditions est vraie :
    * Perte > 3% du capital total en 24h glissantes
    * 3+ erreurs TRADER consécutives sans fill confirmé
    * Exchange health DOWN depuis > 5 minutes
    * Data quality DEGRADED depuis > 15 minutes
    * Gas cost > $1 par transaction (Phase 4 DEX uniquement)
- Quand TRIPPED :
    * TRADING_VALIDATOR vérifie l'état killswitch AVANT tout exec.order.submit
    * Les ordres ouverts ne sont PAS annulés automatiquement — alerte humaine
    * Reprendre le trading nécessite un reset manuel du state killswitch

### Paper trading obligatoire
- Mode PAPER pendant les 30 premiers jours calendaires minimum après chaque
  nouvelle stratégie déployée. TRADING_ENV=paper dans .env.
- Leverage interdit : 1x uniquement. Pas de margin, pas de futures avec levier
  avant 60 jours de paper trading positif validé.
- Toute stratégie non testée en paper = INTERDITE en live sans exception.

### Approbation humaine
- Si OrderPlan.approval.required = true :
    TRADING_VALIDATOR publie sur trading.ops.human.approval.request
    et attend l'ACK Telegram avant d'émettre exec.order.submit.
    Timeout = 10 minutes → ABORT automatique.
- Seuil par défaut : 100€ notionnel en paper, 50€ en live initial.

### Priorité système
- Les agents trading critiques (KILL_SWITCH_GUARDIAN, POLICY_GATEKEEPER, TRADER)
  utilisent exclusivement Haiku — jamais Sonnet ni Opus.
- En cas de rate limit API Anthropic : couper les appels Content Factory
  en premier, jamais les appels trading.
- Le trading-poller est un service Docker séparé (cpu_shares=2048).
  Le content-poller a cpu_shares=512.
- Si le content-poller crash : le trading continue sans impact.
- Si le trading-poller déclenche un kill switch : il reste isolé du content.

### Idempotence et traçabilité
- TRADER vérifie state/trading/exec/pending_orders.json avant chaque envoi.
  Si l'idempotency_key existe avec status=SENT : ne pas renvoyer, log WARNING.
- Tout ce qui touche à une décision (proposal, plan, submit, fill) est copié
  sur trading.audit.* en append-only.
- Le répertoire state/trading/audit/ n'est jamais purgé automatiquement.

### Rotation des fichiers bus
- Les fichiers JSONL trading.raw.*.jsonl : archivés + tronqués tous les 7 jours.
- Les fichiers JSONL trading.intel.*.jsonl : conservés 30 jours.
- Les fichiers trading.audit.*.jsonl : jamais tronqués automatiquement.
- state/trading/ est inclus dans le backup automatique quotidien du VPS.

### Intégration avec le système existant
- scraper.js reste inchangé et continue d'alimenter le Publisher bot.
- NEWS_FEED est un agent séparé avec ses propres sources.
- Le Publisher bot (TELEGRAM_BOT_TOKEN) et le bot Trader-Agents
  (TRADER_TELEGRAM_BOT_TOKEN) coexistent sans conflit.
```

---

## 12. Roadmap par sprints

### Sprint 1 — Semaine 1 : Data pipeline (zéro trade, zéro LLM trading, zéro risque)

| Livrable | Agent | Priorité |
|----------|-------|----------|
| WebSocket Binance réel (BTC/ETH/BNB) | BINANCE_PRICE_FEED | 🔴 |
| Features techniques complètes (RSI, Bollinger, ATR) | MARKET_EYE | 🔴 |
| PREDICTOR Niveau A (scoring statique) | PREDICTOR | 🟠 |
| Bus JSONL + rotation 7j/30j/jamais | infrastructure | 🔴 |

**Validation Sprint 1** : les features circulent dans le bus, les fichiers JSONL grossissent correctement, la rotation fonctionne.

### Sprint 1 — Semaine 2 : News + Alertes

| Livrable | Agent | Priorité |
|----------|-------|----------|
| NEWS_FEED (Nitter + Telegram MTProto + CryptoPanic) | NEWS_FEED | 🔴 |
| NEWS_SCORING (scoring urgence Haiku) | NEWS_SCORING | 🔴 |
| Telegram bot "Trader - Agents" créé + configuré | infrastructure | 🔴 |
| KILL_SWITCH_GUARDIAN branché Telegram | KILL_SWITCH_GUARDIAN | 🔴 |

**Validation Sprint 1 complet** : alerte Telegram reçue quand un compte watchlist tweete, killswitch monitore les health checks.

### Sprint 2 — Semaines 3-4 : Cerveau en paper

| Livrable | Agent |
|----------|-------|
| REGIME_DETECTOR réel (avec news input) | REGIME_DETECTOR |
| TRADE_GENERATOR Haiku (confirmation adaptative) | TRADE_GENERATOR |
| RISK_MANAGER déterministe | RISK_MANAGER |
| POLICY_GATEKEEPER (cooldown + human approval) | POLICY_GATEKEEPER |
| TRADER paper mode (log sans envoyer) | TRADER |
| TRADING_VALIDATOR (vérifie killswitch + boutons Telegram) | TRADING_VALIDATOR |

### Sprint 3 — Mois 2 : Paper trading complet

| Livrable | Agent |
|----------|-------|
| ORDER_RECONCILER + POSITION_MANAGER + TRADE_LOG | Couche 3 complète |
| PERFORMANCE_ANALYST (rapport daily Telegram) | PERFORMANCE_ANALYST |
| LEARNER (post-mortems + missed opportunities) | LEARNER |
| Collecte de 30 jours de données de performance | — |

### Sprint 4 — Mois 3 : Optimisation

| Livrable | Agent |
|----------|-------|
| STRATEGY_TUNER (1x/semaine, Sonnet) | STRATEGY_TUNER |
| DARWIN_SELECTOR (allocation dynamique) | DARWIN_SELECTOR |
| SENTIMENT_ANALYST + ONCHAIN_ANALYST + WHALE_WATCHER | Intelligence complète |
| PORTFOLIO_MANAGER | PORTFOLIO_MANAGER |

### Phase 4 — À définir : Premier trade live

- Capital : 20€ max pour valider le pipeline live
- Conditions : 30 jours paper positifs, killswitch testé, approbation humaine testée
- Débloquer `_deferred/` DEX uniquement si CEX est stable

---

## 13. Estimation des coûts tokens

| Agent | LLM | Modèle | Fréquence | Coût/mois estimé |
|-------|-----|--------|-----------|------------------|
| NEWS_SCORING | ✅ | Haiku | 60 appels/h | ~$2 |
| TRADE_GENERATOR | ✅ | Haiku | 1 appel/min | ~$5 |
| SENTIMENT_ANALYST | ✅ | Haiku | 1 appel/15min | ~$2 |
| PERFORMANCE_ANALYST | ✅ | Haiku | 1 appel/jour | ~$0.5 |
| LEARNER | ✅ | Haiku | 1 appel/jour | ~$0.5 |
| STRATEGY_TUNER | ✅ | Sonnet | 1 appel/semaine | ~$1 |
| BINANCE_PRICE_FEED | ❌ | Code pur | — | $0 |
| MARKET_EYE | ❌ | Code pur | — | $0 |
| PREDICTOR | ❌ | Code pur | — | $0 |
| REGIME_DETECTOR | ❌ | Code pur | — | $0 |
| RISK_MANAGER | ❌ | Code pur | — | $0 |
| POSITION_SIZER | ❌ | Code pur | — | $0 |
| CORRELATION_MANAGER | ❌ | Code pur | — | $0 |
| POLICY_GATEKEEPER | ❌ | Code pur | — | $0 |
| EXCHANGE_HEALTH | ❌ | Code pur | — | $0 |
| KILL_SWITCH_GUARDIAN | ❌ | Code pur | — | $0 |
| TRADER + pipeline exec | ❌ | Code pur | — | $0 |
| DARWIN_SELECTOR | ❌ | Code pur | — | $0 |
| **Total trading LLM** | | | | **~$11/mois** |
| Content Factory (existant) | | | | ~$15-20/mois |
| **Total système** | | | | **~$26-31/mois** |

Budget mensuel restant dans l'enveloppe de ~$55 : **$24-29 de marge**.
**Agents LLM : 6 sur 24 agents (25%). 75% du système tourne en code pur.**

---

*Document de référence — à maintenir dans `workspace/docs/TRADING_ARCHITECTURE.md`*  
*Toute modification architecturale majeure doit mettre à jour ce document avant implémentation.*
