import React, { useState } from 'react';
import { api } from '../api/client';
import { useApiData, timeAgo } from '../hooks';
import { LoadingState, ErrorState, SectionTitle, MetricCard, LastUpdated } from '../components/UI';

// ── PIPELINE DATA ────────────────────────────────────────────────────
const SYSTEM_DATA = [
  {
    id: "trading", label: "Trading", icon: "⚡",
    desc: "Pipeline algorithmique — données → signal → exécution",
    layers: [
      { name: "Données", color: "#38bdf8", agents: [
        { id: "BINANCE_PRICE_FEED", interval: "30s",      llm: null,    desc: "Prix spot BTC/ETH/BNB en temps réel depuis Binance REST API", inputs: [], outputs: ["MARKET_EYE","PREDICTOR"] },
        { id: "NEWS_FEED",          interval: "5min",     llm: null,    desc: "Scrape 6 flux RSS crypto + Fear&Greed + SEC EDGAR", inputs: [], outputs: ["NEWS_SCORING"] },
        { id: "WHALE_FEED",         interval: "5min",     llm: null,    desc: "Transactions whale >500k$ sur Ethereum via Etherscan V2. ETH/WBTC ≥$500k, USDT/USDC ≥$1M", inputs: [], outputs: ["WHALE_ANALYZER"] },
      ]},
      { name: "Analyse", color: "#a78bfa", agents: [
        { id: "MARKET_EYE",      interval: "5min", llm: null,     desc: "Calcule RSI/BB/MACD/ATR/Volume sur bougies 5m, 1h, 4h. Émet bb_width=(upper-lower)/price", inputs: ["BINANCE_PRICE_FEED"], outputs: ["REGIME_DETECTOR","TRADE_GENERATOR"] },
        { id: "NEWS_SCORING",    interval: "5min", llm: "Haiku",  desc: "Score chaque news — urgency/reliability/relevance 0-10. Ignore urgency<3. ~420 tokens/news", inputs: ["NEWS_FEED"], outputs: ["TRADE_GENERATOR"] },
        { id: "WHALE_ANALYZER",  interval: "5min", llm: null,     desc: "Classifie flux whale : TO_EXCHANGE / FROM_EXCHANGE / STABLE_MINT / MM_FLOW. Score [-1,+1] sur 6h glissant", inputs: ["WHALE_FEED"], outputs: ["REGIME_DETECTOR"] },
        { id: "PREDICTOR",       interval: "5min", llm: null,     desc: "Prédit direction court terme par logique pure à partir des indicateurs marché", inputs: ["MARKET_EYE"], outputs: ["TRADE_GENERATOR"] },
        { id: "REGIME_DETECTOR", interval: "5min", llm: null,     desc: "Régime marché : TREND_UP/DOWN/RANGE/PANIC/EUPHORIA/VOLATILE + whale_context (ACCUMULATION/DISTRIBUTION/NEUTRAL)", inputs: ["MARKET_EYE","WHALE_ANALYZER"], outputs: ["TRADE_GENERATOR"] },
      ]},
      { name: "Décision", color: "#fbbf24", agents: [
        { id: "TRADE_GENERATOR",    interval: "5min", llm: "Haiku",  desc: "Génère propositions de trade. Filtre pré-Haiku hasSignal. Ajustement confidence ±0.07 depuis whale_context. ~1600 tokens/appel", inputs: ["MARKET_EYE","NEWS_SCORING","PREDICTOR","REGIME_DETECTOR","STRATEGY_GATEKEEPER"], outputs: ["RISK_MANAGER"] },
        { id: "RISK_MANAGER",       interval: "60s",  llm: null,     desc: "Valide ou bloque : 1% risk max, max 3 positions simultanées, pas de doublon symbol", inputs: ["TRADE_GENERATOR"], outputs: ["POLICY_ENGINE"] },
        { id: "POLICY_ENGINE",      interval: "30s",  llm: null,     desc: "Vérifie règles : asset/stratégie/env/horaire/notional/blacklist. Zéro LLM", inputs: ["RISK_MANAGER","REGIME_DETECTOR","KILL_SWITCH_GUARDIAN"], outputs: ["TRADING_ORCHESTRATOR"] },
        { id: "STRATEGY_GATEKEEPER",interval: "1h",   llm: null,     desc: "Active/désactive stratégies selon score pondéré. Score ≥0.60=active, 0.40-0.59=testing, <0.40=warning Telegram", inputs: ["PERFORMANCE_ANALYST"], outputs: ["TRADE_GENERATOR"] },
      ]},
      { name: "Exécution", color: "#f87171", agents: [
        { id: "KILL_SWITCH_GUARDIAN",  interval: "60s", llm: null, desc: "Surveille drawdown daily. -3% = TRIPPED. Reset manuel uniquement. Bloque POLICY_ENGINE", inputs: [], outputs: ["POLICY_ENGINE","TRADING_ORCHESTRATOR"] },
        { id: "TRADING_ORCHESTRATOR",  interval: "10s", llm: null, desc: "Corrèle order_plan + policy.decision via order_plan_ref. États PENDING→APPROVED/BLOCKED/EXPIRED", inputs: ["POLICY_ENGINE"], outputs: ["TESTNET_EXECUTOR"] },
        { id: "TESTNET_EXECUTOR",      interval: "30s", llm: null, desc: "Ordre MARKET sur Binance Testnet + OCO (TP+SL) automatique. Écrit positions_testnet.json + ledger", inputs: ["TRADING_ORCHESTRATOR"], outputs: ["TRADING_PUBLISHER","PERFORMANCE_ANALYST"] },
        { id: "PAPER_EXECUTOR",        interval: "30s", llm: null, desc: "Simule l'exécution en paper trading — désactivé, remplacé par TESTNET_EXECUTOR", inputs: ["TRADING_ORCHESTRATOR"], outputs: ["TRADING_PUBLISHER"], skip: true },
      ]},
      { name: "Publication", color: "#34d399", agents: [
        { id: "TRADING_PUBLISHER", interval: "60s", llm: "Haiku", desc: "Publie positions et bilans sur Telegram @CryptoRizonTrader_bot. Ouverture/fermeture immédiates, bilan quotidien 21h UTC", inputs: ["TESTNET_EXECUTOR"], outputs: ["@CryptoRizonTrader"] },
      ]},
      { name: "Optimisation", color: "#fb923c", agents: [
        { id: "PERFORMANCE_ANALYST",  interval: "1h",      llm: null,     desc: "Calcule métriques par stratégie/asset/régime. Produit strategy_performance.json, global_performance.json, etc.", inputs: ["TESTNET_EXECUTOR"], outputs: ["STRATEGY_GATEKEEPER","TRADE_STRATEGY_TUNER"] },
        { id: "STRATEGY_RESEARCHER",  interval: "1j",      llm: "Sonnet", desc: "Scrape Reddit (r/algotrading, r/CryptoMarkets). Score Reddit >50. ~3000 tokens/run", inputs: [], outputs: ["STRATEGY_GATEKEEPER"] },
        { id: "TRADE_STRATEGY_TUNER", interval: "1 sem.",  llm: "Sonnet", desc: "Attend 30 trades min. Affine 1 paramètre à la fois (RSI±3, BB±0.03). Rollback auto. Anti-oscillation blacklist", inputs: ["PERFORMANCE_ANALYST"], outputs: ["TRADE_GENERATOR"] },
        { id: "GLOBAL_TOKEN_TRACKER", interval: "1h",      llm: null,     desc: "Agrège token_costs.jsonl. Bilan Telegram 20h UTC sur @OppenCllaw_Bot", inputs: ["Tous les agents LLM"], outputs: ["@OppenCllaw_Bot"] },
        { id: "GLOBAL_TOKEN_ANALYST", interval: "lun+jeu", llm: "Sonnet", desc: "Analyse coûts tokens, propose optimisations. Lundi + jeudi 8h UTC", inputs: ["GLOBAL_TOKEN_TRACKER"], outputs: ["@OppenCllaw_Bot"] },
      ]},
    ]
  },
  {
    id: "content", label: "Content", icon: "📡",
    desc: "Pipeline de publication CryptoRizon — scraping → rédaction → publication",
    layers: [
      { name: "Scraping", color: "#38bdf8", agents: [
        { id: "hourly_scraper", interval: "1h (7h–23h)", llm: "Haiku", desc: "Scrape 6 flux RSS crypto, traduit en français via Haiku, crée des drafts Telegram. Dedup séquentiel", inputs: [], outputs: ["drafts.js"], type: "script" },
        { id: "scraper",        interval: "manuel",      llm: "Haiku", desc: "Scrape approfondi à la demande. Même sources RSS, même pipeline de traduction", inputs: [], outputs: ["drafts.js"], type: "script" },
      ]},
      { name: "Pipeline", color: "#a78bfa", agents: [
        { id: "drafts.js", interval: "module partagé", llm: null, desc: "Module partagé de gestion des drafts (IDs #1–#100, TTL 24h). Utilisé par poller et hourly_scraper", inputs: ["hourly_scraper","scraper"], outputs: ["poller.js"], type: "script" },
        { id: "poller.js", interval: "continu",        llm: null, desc: "Écoute le bot Telegram Publisher. Déclenche la sélection, génération de post et publication", inputs: ["drafts.js"], outputs: ["copywriter","twitter.js"], type: "poller" },
      ]},
      { name: "Rédaction", color: "#fbbf24", agents: [
        { id: "copywriter", interval: "à la demande", llm: "Sonnet", desc: "Rédige les posts dans le style Ogilvy/Halbert/Stan Leloup. Max 600 caractères. Source injectée via SOURCE_MAP", inputs: ["poller.js"], outputs: ["twitter.js","Telegram @CryptoRizon"] },
      ]},
      { name: "Publication", color: "#34d399", agents: [
        { id: "twitter.js", interval: "sur validation", llm: null, desc: "Poste sur @CryptoRizon via OAuth 1.0a + API v1.1 (image upload). Publie simultanément sur Telegram", inputs: ["copywriter"], outputs: ["Twitter @CryptoRizon","Telegram @CryptoRizon"], type: "script" },
      ]},
    ]
  },
  {
    id: "system", label: "Système", icon: "🛡",
    desc: "Infrastructure, surveillance et maintenance automatique",
    layers: [
      { name: "Surveillance", color: "#34d399", agents: [
        { id: "SYSTEM_WATCHDOG", interval: "15min", llm: null, desc: "Surveille process, agents, disque et bus — alerte immédiate WARN/CRIT + rapport quotidien 08h UTC", inputs: ["Tous les agents"], outputs: ["@OppenCllaw_Bot"] },
      ]},
      { name: "Pollers", color: "#fbbf24", agents: [
        { id: "trading/poller.js", interval: "continu", llm: null, desc: "Orchestre les agents trading selon leurs schedules. Séquentiel — un agent bloqué bloque tous les suivants. SIGKILL sur timeout", inputs: [], outputs: ["Tous les agents trading"], type: "poller" },
        { id: "content/poller.js", interval: "continu", llm: null, desc: "Orchestre le pipeline content CryptoRizon. Écoute le bot Publisher Telegram", inputs: [], outputs: ["Tous les agents content"], type: "poller" },
      ]},
      { name: "Maintenance", color: "#f87171", agents: [
        { id: "bus_cleanup_trading", interval: "03h30 UTC",    llm: null, desc: "Nettoyage bus trading. Rétentions : market_features 2j, raw_ticker 1j, intel_regime 90j, ledger 365j", inputs: [], outputs: ["state/trading/bus/"], type: "cron" },
        { id: "cleanup.js",          interval: "à la demande", llm: null, desc: "Purge des données content selon RETENTION.md", inputs: [], outputs: ["state/content/"], type: "script" },
      ]},
    ]
  },
];

// ── CONTEXT BUNDLES ──────────────────────────────────────────────────
const CONTEXT_BUNDLES = [
  {
    id: "infra",
    title: "CONTEXT_BUNDLE_INFRA",
    subtitle: "VPS · Docker · Arborescence · Permissions",
    color: "#38bdf8",
    icon: "🖥",
    content: `# CONTEXT_BUNDLE_INFRA — Infrastructure OpenClaw
> Dernière mise à jour : 2026-03-09

## 1. VPS & OS
| Paramètre | Valeur |
|---|---|
| Hébergeur | Hostinger |
| OS | Ubuntu 22.04 LTS |
| User SSH | openclawadmin |
| Runtime | Node.js v22 |
| Orchestrateur | Docker + Docker Compose |

## 2. Docker
Conteneur principal : openclaw-openclaw-gateway-1
Port exposé         : 18789
User interne        : node (uid=1000)
Image               : ghcr.io/openclaw/openclaw:2026.3.2

Commandes essentielles :
  docker ps
  docker exec openclaw-openclaw-gateway-1 node /path/to/script.js
  cd /home/openclawadmin/openclaw && docker compose down && docker compose up -d
  docker compose restart   # NE recharge PAS le .env

⚠️ RÈGLE : toute nouvelle variable .env nécessite un docker compose down && up complet.

## 3. Permissions fichiers
| Propriétaire | Fichiers | Règle |
|---|---|---|
| root | .env, docker-compose.yml | NE JAMAIS MODIFIER directement |
| openclawadmin | /home/openclawadmin/openclaw/ | Fichiers host |
| node (uid=1000) | /home/node/.openclaw/workspace/ | Fichiers dans le conteneur |

## 4. Arborescence globale
/home/openclawadmin/openclaw/           ← repo OpenClaw officiel (NE PAS PUSHER ICI)
/home/openclawadmin/openclaw/workspace/ ← repo GitHub NoFiix/openclaw-workspace ✅
    ├── .env
    ├── skills_custom/
    │   ├── poller.js
    │   ├── scraper.js
    │   ├── hourly_scraper.js
    │   ├── drafts.js
    │   └── trading/
    │       ├── poller.js
    │       ├── _shared/
    │       │   ├── agentRuntime.js
    │       │   ├── bus.js
    │       │   ├── state.js
    │       │   ├── envelope.js
    │       │   └── logTokens.js
    │       ├── BINANCE_PRICE_FEED/
    │       ├── MARKET_EYE/
    │       └── ...
    └── state/
        └── trading/
            ├── bus/
            ├── exec/
            ├── learning/
            ├── memory/
            ├── schedules/
            └── runs/

## 5. Variables d'environnement (.env)
ANTHROPIC_API_KEY
OPENAI_API_KEY
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
TRADER_TELEGRAM_BOT_TOKEN / TRADER_TELEGRAM_CHAT_ID
BUILDER_TELEGRAM_BOT_TOKEN / BUILDER_TELEGRAM_CHAT_ID
TWITTER_API_KEY / TWITTER_API_SECRET
TWITTER_ACCESS_TOKEN / TWITTER_ACCESS_TOKEN_SECRET
BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_SECRET_KEY
BINANCE_TESTNET_BASE_URL=https://testnet.binance.vision
TRADING_MODE=testnet

## 6. Pollers actifs
Restart trading poller :
  bash skills_custom/trading/restart_trading_poller.sh

⚠️ restart_trading_poller.sh NE redirige PAS les logs.
Pour logs : docker exec -d openclaw-openclaw-gateway-1 sh -c "node poller.js >> poller.log 2>&1"

## 7. Cron jobs
30 3 * * * docker exec openclaw-openclaw-gateway-1 node \\
  /home/node/.openclaw/workspace/skills_custom/trading/bus_cleanup_trading.js \\
  >> /home/openclawadmin/logs/cleanup_trading.log 2>&1

## 8. Routage modèles LLM
Score 3-4  → claude-haiku-4-5-20251001
Score 5-6  → gpt-4o-mini
Score 7-8  → gpt-4o
Score 9-11 → claude-sonnet-4-20250514
Score 12-15→ claude-opus-4-20250514
FORCE_OPUS pour code/debug — FORCE_SONNET pour copywriting.

## 9. GitHub
cd /home/openclawadmin/openclaw/workspace/
git add -A && git commit -m "message" && git push
Remote : NoFiix/openclaw-workspace
⚠️ JAMAIS depuis /home/openclawadmin/openclaw/

## 10. Règles architecture
- Agent = entité autonome avec mémoire + SOUL.md + AGENTS.md + KPI
- Skill = compétence réutilisable sans mémoire
- Agents transversaux : préfixe GLOBAL_

## 11. Règles poller trading
- Poller tourne DANS le container (docker exec -d ...)
- Séquentiel — un agent bloqué bloque tous les suivants
- jitter_seconds > 60 sur agents daily/weekly = blocage → toujours 0 pour every_seconds > 3600
- ctx.state : jamais readJSON/writeJSON direct
- Etherscan V2 : https://api.etherscan.io/v2/api?chainid=1 (V1 dépréciée)
- DASHBOARD PM2 : jamais "pm2 restart" — toujours pm2 delete + pm2 start + pm2 save`,
  },
  {
    id: "trading",
    title: "CONTEXT_BUNDLE_TRADING",
    subtitle: "Agents · Pipeline · Schedules · Coûts",
    color: "#f59e0b",
    icon: "⚡",
    content: `# CONTEXT_BUNDLE_TRADING — Système Trading OpenClaw
> Dernière mise à jour : 2026-03-09

## 1. Vue d'ensemble
Mode : testnet (vrais ordres API, argent fictif)
Symbols : BTCUSDT, ETHUSDT, BNBUSDT
Timeframes : 5m, 1h, 4h
Capital fictif : 10 000 USDT
Risque par trade : 1% ($100)
Max positions simultanées : 3

## 2. Pipeline — flux de données
BINANCE_PRICE_FEED (30s)   → bus: trading.raw.market.ticker
MARKET_EYE (300s)          → bus: trading.intel.market.features
NEWS_FEED (300s)           → bus: trading.raw.news.article
NEWS_SCORING (300s)        → bus: trading.intel.news.event
WHALE_FEED (300s)          → bus: trading.raw.whale.transfer
WHALE_ANALYZER (300s)      → bus: trading.intel.whale.signal
REGIME_DETECTOR (300s)     → bus: trading.intel.regime v2
TRADE_GENERATOR (300s)     → bus: trading.strategy.trade.proposal
RISK_MANAGER (60s)         → bus: trading.strategy.order.plan
POLICY_ENGINE (30s)        → bus: trading.strategy.policy.decision
TRADING_ORCHESTRATOR (10s) → bus: trading.exec.order.submit
TESTNET_EXECUTOR (30s)     → bus: trading.exec.position.snapshot + trade.ledger
KILL_SWITCH_GUARDIAN (60s) → bus: trading.ops.killswitch.state

## 3. Schedules
BINANCE_PRICE_FEED  : 30s
TESTNET_EXECUTOR    : 30s
KILL_SWITCH_GUARDIAN: 60s
RISK_MANAGER        : 60s
TRADING_PUBLISHER   : 60s
NEWS_FEED           : 300s
NEWS_SCORING        : 300s
MARKET_EYE          : 300s
PREDICTOR           : 300s
WHALE_FEED          : 300s (jitter 15s)
WHALE_ANALYZER      : 300s (jitter 60s)
REGIME_DETECTOR     : 300s
TRADE_GENERATOR     : 300s
PERFORMANCE_ANALYST : 3600s
STRATEGY_GATEKEEPER : 3600s
GLOBAL_TOKEN_TRACKER: 3600s
TRADE_STRATEGY_TUNER: 604800s (1x/sem, attend 30 trades)
STRATEGY_RESEARCHER : 86400s (1x/jour)

## 4. Coûts tokens
TRADE_GENERATOR      : ~$0.003/appel Haiku, ~3 appels/cycle si signal
NEWS_SCORING         : ~$0.0007/news Haiku
STRATEGY_RESEARCHER  : ~$0.01/jour Sonnet
TRADE_STRATEGY_TUNER : ~$0.05/semaine Sonnet (si 30+ trades)
Projection mensuelle : ~$12-15/mois

## 5. Fichiers clés
cat state/trading/exec/positions_testnet.json
cat state/trading/exec/daily_pnl_testnet.json
cat state/trading/learning/global_performance.json
cat state/trading/learning/strategy_performance.json
cat state/trading/memory/WHALE_ANALYZER.state.json
cat state/trading/exec/killswitch.json
cat state/trading/learning/token_summary.json

## 6. Roadmap
Sprint 1 ✅ : BINANCE_PRICE_FEED, MARKET_EYE, PREDICTOR, KILL_SWITCH, NEWS_FEED, NEWS_SCORING
Sprint 2 ✅ : REGIME_DETECTOR
Sprint 3 ✅ : PAPER_EXECUTOR, RISK_MANAGER, PERFORMANCE_ANALYST
Sprint 4 ✅ : PERFORMANCE_ANALYST, STRATEGY_RESEARCHER, STRATEGY_GATEKEEPER, TRADE_GENERATOR v3
Sprint 5 ✅ : TESTNET_EXECUTOR, connexion Binance Testnet
Sprint 6 ✅ : TRADE_STRATEGY_TUNER v3, renommage STRATEGY_GATEKEEPER
Sprint 7 ✅ : WHALE_FEED + WHALE_ANALYZER + REGIME_DETECTOR v2
Sprint 8 ✅ : POLICY_ENGINE + TRADING_ORCHESTRATOR
Sprint 9 🔲 : Trading réel on-chain (SCALPER/INTRADAY/SWING)
Sprint 10 🔲: ERC-8004 + stratégie NewsMomentum

## 7. Bus cleanup (rétentions)
market_features          : 2 jours
raw_market_ticker        : 1 jour
intel_prediction         : 7 jours
raw_whale_transfer       : 2 jours
intel_whale_signal       : 7 jours
exec_position_snapshot   : 30 jours
intel_regime             : 90 jours
exec_trade_ledger        : 365 jours`,
  },
  {
    id: "content",
    title: "CONTEXT_BUNDLE_CONTENT",
    subtitle: "Content Factory · Scraper · Drafts · Poller",
    color: "#10b981",
    icon: "📡",
    content: `# CONTEXT_BUNDLE_CONTENT — Content Factory OpenClaw
> Dernière mise à jour : 2026-03-09

## 1. Architecture Content Pipeline V1

Composants actifs :
- scraper.js      : 6 sources RSS, traduction Haiku, dedup séquentiel
- hourly_scraper.js: scrape horaire 7h–23h UTC
- drafts.js       : module partagé — IDs #1–#100, TTL 24h
- poller.js       : écoute bot Telegram Publisher
- twitter.js      : OAuth 1.0a, image upload API v1.1

Règles éditoriales :
- Posts cappés à 600 caractères
- Style : Ogilvy / Gary Halbert / Stan Leloup
- Source injectée via SOURCE_MAP dans le code (pas par Claude)
- Langue : français

Sources RSS (6) : CoinDesk, CoinTelegraph, Decrypt, The Block, Blockworks, CryptoSlate

Bots Telegram :
- Publisher bot : BUILDER_TELEGRAM_BOT_TOKEN + BUILDER_TELEGRAM_CHAT_ID
- Canal : @CryptoRizon

## 2. Système de Drafts
- IDs séquentiels #1 à #100 (rotation)
- TTL : 24 heures
- États : available / published / rejected
- Fichier : state/drafts.json

Workflow :
  hourly_scraper → crée draft (ID auto) → drafts.js
  poller.js → lit drafts disponibles → propose via Telegram
  Daniel valide → copywriter génère → twitter.js publie

## 3. Content Factory V2 (en développement)
10 agents, 3 couches :

Couche 0 — Orchestration : ORCHESTRATOR (Opus, rôle COO)
Couche 1 — Intelligence  : ANALYST, STRATEGIST (mode sprint 20-30 scripts)
Couche 2 — Production    : WRITER, VISUAL, VOICE, VIDEO, QA
Couche 3 — Optimisation  : PERFORMANCE, IMPROVER

Structure fichiers :
  workspace/agents/{agent}/
  workspace/projects/videos/{date_sujet}/
  workspace/improvements/pending/ | applied/ | rejected/

États workflow : draft → review → approved → rejected → revision

## 4. Coûts Content Pipeline
hourly_scraper (traduction) : ~$0.002/run × 16 runs/jour = ~$0.03/jour
copywriter (Sonnet)         : ~$0.01/post × 3 posts/jour = ~$0.03/jour
Projection mensuelle        : ~$2-3/mois

## 5. Twitter @CryptoRizon
- API : OAuth 1.0a (TWITTER_API_KEY + ACCESS_TOKEN)
- Upload image : API v1.1 (chunked)
- Publication texte : API v2
- 187 posts publiés (mars 2026)`,
  },
];

const TYPE_LABEL = { script: "SCRIPT", poller: "POLLER", cron: "CRON" };
const TYPE_COLOR = { script: "var(--blue)", poller: "var(--amber)", cron: "var(--purple)" };

// ── DETAIL PANEL ─────────────────────────────────────────────────────
function DetailPanel({ agent }) {
  const sectionLabel = {
    fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 600,
    letterSpacing: ".15em", textTransform: "uppercase", color: "var(--text-secondary)", marginBottom: 6,
  };

  if (!agent) return (
    <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}>
      <div style={{ padding: "32px 20px", textAlign: "center" }}>
        <div style={{ fontSize: 28, marginBottom: 12, opacity: 0.2, color: "var(--text-secondary)" }}>◎</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          Sélectionne un agent<br />pour voir ses connexions
        </div>
      </div>
      <div style={{ borderTop: "1px solid var(--border)", padding: "14px 16px" }}>
        <div style={{ ...sectionLabel, marginBottom: 10 }}>Légende</div>
        {[
          { color: "#38bdf8", label: "Données / Scraping" },
          { color: "#a78bfa", label: "Analyse / Pipeline" },
          { color: "#fbbf24", label: "Décision / Rédaction" },
          { color: "#f87171", label: "Exécution" },
          { color: "#34d399", label: "Publication" },
          { color: "#fb923c", label: "Optimisation" },
        ].map(l => (
          <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: l.color, flexShrink: 0 }} />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-secondary)" }}>{l.label}</span>
          </div>
        ))}
        <div style={{ borderTop: "1px solid var(--border)", marginTop: 10, paddingTop: 10 }}>
          {[["IN", "Fournit cet agent"], ["OUT", "Reçoit de cet agent"]].map(([t, d]) => (
            <div key={t} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, color: "var(--text-secondary)", width: 24 }}>{t}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>{d}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  return (
    <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden" }}>
      <div style={{ height: 3, background: agent.layerColor }} />
      <div style={{ padding: 16 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600, color: agent.layerColor, letterSpacing: ".1em", textTransform: "uppercase", marginBottom: 4 }}>
          {agent.systemLabel} · {agent.layerName}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8, lineHeight: 1.3, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {agent.id}
          {agent.skip && <span style={{ fontSize: 9, color: "var(--amber)", fontWeight: 600 }}>SKIP</span>}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.65, marginBottom: 14 }}>
          {agent.desc}
        </div>

        {/* Fréquence + LLM */}
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14, gap: 8 }}>
          <div>
            <div style={sectionLabel}>Fréquence</div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600, color: "var(--text-primary)" }}>{agent.interval}</span>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={sectionLabel}>LLM</div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600, color: agent.llm ? "var(--amber)" : "var(--green)" }}>
              {agent.llm ?? "Aucun"}
            </span>
          </div>
        </div>

        {/* Type */}
        {agent.type && (
          <div style={{ marginBottom: 14 }}>
            <div style={sectionLabel}>Type</div>
            <span style={{
              display: "inline-block", fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
              padding: "2px 7px", borderRadius: "var(--radius)",
              background: `${TYPE_COLOR[agent.type]}18`, color: TYPE_COLOR[agent.type],
              letterSpacing: ".05em", textTransform: "uppercase",
            }}>
              {TYPE_LABEL[agent.type]}
            </span>
          </div>
        )}

        {/* Inputs */}
        {agent.inputs?.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={sectionLabel}>Reçoit depuis</div>
            {agent.inputs.map(inp => (
              <div key={inp} style={{
                display: "flex", alignItems: "center", gap: 5, padding: "4px 8px",
                borderRadius: "var(--radius)", fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 500,
                color: agent.layerColor, background: `${agent.layerColor}12`, marginBottom: 4,
              }}>
                <span style={{ opacity: 0.5, fontSize: 10 }}>↓</span> {inp}
              </div>
            ))}
          </div>
        )}

        {/* Outputs */}
        {agent.outputs?.length > 0 && (
          <div style={{ marginBottom: agent.skip ? 12 : 0 }}>
            <div style={sectionLabel}>Envoie vers</div>
            {agent.outputs.map(out => (
              <div key={out} style={{
                display: "flex", alignItems: "center", gap: 5, padding: "4px 8px",
                borderRadius: "var(--radius)", fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 500,
                color: "var(--green)", background: "rgba(16,185,129,0.1)", marginBottom: 4,
              }}>
                <span style={{ opacity: 0.5, fontSize: 10 }}>→</span> {out}
              </div>
            ))}
          </div>
        )}

        {agent.skip && (
          <div style={{
            background: "var(--amber-glow)", border: "1px solid var(--amber-dim)",
            borderRadius: "var(--radius)", padding: "8px 10px",
            fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--amber)", fontWeight: 500,
          }}>
            ⚠ Agent désactivé (SKIP)
          </div>
        )}
      </div>
    </div>
  );
}

// ── BUNDLE MODAL ─────────────────────────────────────────────────────
function BundleModal({ bundle, onClose }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard?.writeText(bundle.content).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  React.useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200, backdropFilter: "blur(4px)" }}
      onClick={onClose}
    >
      <div
        style={{ background: "var(--bg-surface)", border: "1px solid var(--border-bright)", borderRadius: "var(--radius)", width: 760, maxWidth: "95vw", maxHeight: "88vh", display: "flex", flexDirection: "column", overflow: "hidden" }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
          <div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: bundle.color }}>
              {bundle.icon} {bundle.title}
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-secondary)", marginTop: 2 }}>
              {bundle.subtitle} · Échap pour fermer
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              onClick={handleCopy}
              style={{
                background: copied ? "var(--green)" : "var(--amber-glow)",
                border: `1px solid ${copied ? "var(--green)" : "var(--amber-dim)"}`,
                color: copied ? "#000" : "var(--amber)",
                padding: "5px 14px", borderRadius: "var(--radius)",
                fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700,
                cursor: "pointer", letterSpacing: ".06em", transition: "all .15s",
              }}
            >
              {copied ? "✓ COPIÉ" : "⎘ COPIER"}
            </button>
            <button
              onClick={onClose}
              style={{ background: "none", border: "1px solid var(--border)", color: "var(--text-secondary)", width: 26, height: 26, borderRadius: "var(--radius)", cursor: "pointer", fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center" }}
            >✕</button>
          </div>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
          <pre style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.75, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {bundle.content}
          </pre>
        </div>
      </div>
    </div>
  );
}

// ── MAIN COMPONENT ────────────────────────────────────────────────────
export default function SystemMap() {
  const [filter,     setFilter]     = useState("all");
  const [activeId,   setActiveId]   = useState(null);
  const [openBundle, setOpenBundle] = useState(null);

  const fetchFn = React.useCallback(() => api.health(), []);
  const { data, loading, lastUpdated } = useApiData(fetchFn, 30000);

  // Runtime status map from API
  const statusMap = {};
  (data?.agents ?? []).forEach(a => { statusMap[a.name] = a; });

  // Full agent detail map from SYSTEM_DATA
  const agentDetailMap = {};
  for (const sys of SYSTEM_DATA)
    for (const layer of sys.layers)
      for (const ag of layer.agents)
        agentDetailMap[ag.id] = { ...ag, layerColor: layer.color, layerName: layer.name, systemLabel: sys.label };

  const activeAgent = activeId ? agentDetailMap[activeId] : null;
  const isInput  = id => activeAgent?.inputs?.includes(id);
  const isOutput = id => activeAgent?.outputs?.includes(id);
  const handleClick = id => setActiveId(prev => prev === id ? null : id);
  const activeSystem = SYSTEM_DATA.find(s => s.id === filter);

  // Summary counts
  const knownNames = Object.keys(agentDetailMap);
  const totalAll  = knownNames.length;
  const totalOk   = knownNames.filter(n => statusMap[n]?.status === "ok").length;
  const totalWarn = knownNames.filter(n => statusMap[n]?.status === "warn").length;
  const totalErr  = knownNames.filter(n => statusMap[n]?.status === "error").length;

  // Render one agent tile
  const renderTile = (agent, layer) => {
    const isActive = activeId === agent.id;
    const inp      = isInput(agent.id);
    const out      = isOutput(agent.id);
    const isDimmed = !!(activeId && !isActive && !inp && !out);
    const rtStatus = statusMap[agent.id]?.status ?? "unknown";

    return (
      <div
        key={agent.id}
        onClick={() => handleClick(agent.id)}
        style={{
          background: isActive ? "var(--bg-hover)" : "var(--bg-elevated)",
          border: `1px solid ${isActive ? layer.color : inp ? "#38bdf8" : out ? "var(--green)" : "var(--border)"}`,
          boxShadow: isActive ? `0 0 0 1px ${layer.color}` : inp ? "0 0 0 1px #38bdf8" : out ? "0 0 0 1px var(--green)" : "none",
          borderRadius: "var(--radius)",
          padding: "10px 12px",
          cursor: "pointer",
          transition: "all .15s",
          opacity: isDimmed ? 0.2 : agent.skip ? 0.45 : 1,
          position: "relative",
        }}
      >
        {inp && <span style={{ position: "absolute", top: 7, right: 8, fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 700, color: layer.color, letterSpacing: ".06em" }}>IN</span>}
        {out && !inp && <span style={{ position: "absolute", top: 7, right: 8, fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 700, color: "var(--green)", letterSpacing: ".06em" }}>OUT</span>}

        {agent.type && (
          <div style={{ display: "inline-block", fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 600, padding: "1px 5px", borderRadius: "var(--radius)", background: `${TYPE_COLOR[agent.type]}18`, color: TYPE_COLOR[agent.type], marginBottom: 4, letterSpacing: ".05em", textTransform: "uppercase" }}>
            {TYPE_LABEL[agent.type]}
          </div>
        )}

        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 4, marginBottom: 3 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600, lineHeight: 1.3, color: isActive ? layer.color : "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {agent.id}
          </div>
          <span
            className={`pulse-dot ${rtStatus === "ok" ? "" : rtStatus === "warn" ? "amber" : rtStatus === "error" ? "red" : "grey"}`}
            style={{
              width: 6, height: 6, borderRadius: "50%", flexShrink: 0, marginTop: 3, display: "inline-block",
              background: rtStatus === "ok" ? "var(--green)" : rtStatus === "warn" ? "var(--amber)" : rtStatus === "error" ? "var(--red)" : "var(--text-muted)",
              boxShadow: rtStatus === "ok" ? "0 0 5px var(--green)" : rtStatus === "warn" ? "0 0 5px var(--amber)" : "none",
            }}
          />
        </div>

        <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-secondary)" }}>
          {agent.interval}
        </div>
        {agent.llm && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--amber)", marginTop: 2, fontWeight: 600 }}>{agent.llm}</div>
        )}
        {agent.skip && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--amber)", marginTop: 2 }}>SKIP</div>
        )}
      </div>
    );
  };

  return (
    <div>
      {openBundle && <BundleModal bundle={openBundle} onClose={() => setOpenBundle(null)} />}

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
        <MetricCard label="Actifs"   value={loading ? "—" : `${totalOk}/${totalAll}`} color="green"  sub="agents en cours" />
        <MetricCard label="Warning"  value={loading ? "—" : totalWarn} color="amber" sub="à vérifier" />
        <MetricCard label="Erreurs"  value={loading ? "—" : totalErr}  color="red"   sub="en échec" />
        <MetricCard label="Systèmes" value={SYSTEM_DATA.length} sub={`${totalAll} agents total`} />
      </div>

      {/* Filter bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, paddingBottom: 20, flexWrap: "wrap" }}>
        {[{ id: "all", label: "Tous les agents", icon: "" }, ...SYSTEM_DATA.map(s => ({ id: s.id, label: s.label, icon: s.icon }))].map(f => (
          <button
            key={f.id}
            onClick={() => { setFilter(f.id); setActiveId(null); }}
            style={{
              display: "flex", alignItems: "center", gap: 6, padding: "6px 14px",
              background: filter === f.id ? "var(--amber-glow)" : "var(--bg-elevated)",
              border: `1px solid ${filter === f.id ? "var(--amber)" : "var(--border)"}`,
              borderRadius: "var(--radius)",
              fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: filter === f.id ? 600 : 400,
              color: filter === f.id ? "var(--amber)" : "var(--text-secondary)",
              cursor: "pointer", transition: "all .12s", letterSpacing: ".04em",
            }}
          >
            {f.icon && <span>{f.icon}</span>}{f.label}
          </button>
        ))}
      </div>

      {/* Main layout: grid + panel */}
      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>

          {/* ALL — flat grouped by system */}
          {filter === "all" && SYSTEM_DATA.map(sys => (
            <div key={sys.id} style={{ marginBottom: 32 }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600, letterSpacing: ".15em", textTransform: "uppercase", color: "var(--text-secondary)", marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
                <span>{sys.icon}</span><span>{sys.label}</span>
                <span style={{ flex: 1, height: 1, background: "var(--border)", display: "block" }} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(168px, 1fr))", gap: 8 }}>
                {sys.layers.flatMap(layer => layer.agents.map(agent => renderTile(agent, layer)))}
              </div>
            </div>
          ))}

          {/* FILTERED — layered view */}
          {filter !== "all" && activeSystem && (
            <div>
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>
                  {activeSystem.icon} {activeSystem.label} System
                </div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{activeSystem.desc}</div>
              </div>
              {activeSystem.layers.map((layer, li) => (
                <div key={layer.name}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <div style={{ width: 7, height: 7, borderRadius: "50%", background: layer.color, flexShrink: 0 }} />
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: layer.color }}>
                      {layer.name}
                    </div>
                    <div style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-muted)" }}>
                      {layer.agents.filter(a => !a.skip).length} agent{layer.agents.filter(a => !a.skip).length !== 1 ? "s" : ""}
                    </div>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(168px, 1fr))", gap: 8, paddingLeft: 15 }}>
                    {layer.agents.map(agent => renderTile(agent, layer))}
                  </div>
                  {li < activeSystem.layers.length - 1 && (
                    <div style={{ paddingLeft: 15, marginTop: 8, marginBottom: 16, color: "var(--border-bright)", fontSize: 14 }}>↓</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Detail panel */}
        <div style={{ width: 256, minWidth: 256, position: "sticky", top: 0 }}>
          <DetailPanel agent={activeAgent} />
        </div>
      </div>

      {/* Context Bundles */}
      <div style={{ marginTop: 40 }}>
        <SectionTitle>Context Bundles</SectionTitle>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-secondary)", marginBottom: 14 }}>
          Fichiers de contexte à coller en début de session Claude — cliquer pour lire et copier
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          {CONTEXT_BUNDLES.map(bundle => (
            <div
              key={bundle.id}
              onClick={() => setOpenBundle(bundle)}
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", overflow: "hidden", cursor: "pointer", transition: "border-color .15s" }}
              onMouseEnter={e => e.currentTarget.style.borderColor = "var(--border-bright)"}
              onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}
            >
              <div style={{ height: 2, background: bundle.color }} />
              <div style={{ padding: "14px 16px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                  <span style={{ fontSize: 20 }}>{bundle.icon}</span>
                  <div>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600, color: "var(--text-primary)" }}>{bundle.title}</div>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-secondary)", marginTop: 1 }}>{bundle.subtitle}</div>
                  </div>
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: bundle.color, letterSpacing: ".08em", textTransform: "uppercase", fontWeight: 600 }}>
                  Cliquer pour lire ↗
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
        <LastUpdated ts={lastUpdated} />
      </div>
    </div>
  );
}
