# dashboard.md — Dashboard OpenClaw

**Date** : 2026-03-15
**Scope** : Backend API (Express.js) + Frontend (React/Vite) du dashboard de monitoring

---

## Résumé exécutif

Le dashboard OpenClaw est une application Express.js (port 3001, localhost) + React/Vite servie par nginx. Il expose **17 endpoints GET** répartis sur 7 fichiers de routes, consommés par **8 pages frontend**. L'authentification se fait par `x-api-key` header. Le dashboard lit directement les fichiers d'état du VPS (state/, POLY_FACTORY/state/) — pas de base de données. [OBSERVÉ]

---

## Architecture backend

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Framework | Express.js 4.19.2 | [OBSERVÉ] |
| Port | 3001 (127.0.0.1 — localhost only) | [OBSERVÉ] |
| Reverse proxy | nginx sur `[2a02:4780:7:c72f::1]:80` → `http://127.0.0.1:3001` | [OBSERVÉ] |
| Auth | `x-api-key` header obligatoire sur toutes les routes | [OBSERVÉ] |
| CORS | `ALLOWED_ORIGIN` (Vercel), `localhost:5173`, `localhost:4173` | [OBSERVÉ] |
| Méthodes | GET uniquement | [OBSERVÉ] |
| Dépendances | express, cors, dotenv (3 deps, minimal) | [OBSERVÉ] |
| PM2 | `dashboard-api` (ID 3), online 44h, 94 Mo RAM, 2 restarts | [OBSERVÉ] |

---

## Endpoints API

### Routes Health & Infrastructure

| Endpoint | Cache TTL | Données lues | Retourne | Tag |
|----------|-----------|-------------|----------|-----|
| `GET /api/health` | 15s | state/trading/schedules/*.json, health_snapshot.json, disk stats | score, crits, warns, agents (21+), pollers, disk, poly_orchestrator | [OBSERVÉ] |
| `GET /api/storage/summary` | 5 min | df -h, du state/ | disk {total, used, free, pct}, sizes par répertoire | [OBSERVÉ] |
| `GET /api/storage/history` | 15 min | aggregates/ | 30 jours historique stockage | [OBSERVÉ] |

### Routes Trading

| Endpoint | Cache TTL | Données lues | Retourne | Tag |
|----------|-----------|-------------|----------|-----|
| `GET /api/trading/live` | 30s | memory/*.state.json, killswitch.json, positions_testnet.json, trade_ledger.jsonl | kill_switch, regime, positions, last_trade, pnl_today, trades_today | [OBSERVÉ] |
| `GET /api/trading/trades` | 60s | trade_ledger.jsonl | Tous les trades fermés normalisés (id, symbol, side, pnl, cum_pnl) | [OBSERVÉ] |
| `GET /api/trading/performance` | 60s | global_performance.json, strategy_performance.json, asset_performance.json | win_rate, profit_factor, Sharpe, drawdown par stratégie et par asset | [OBSERVÉ] |
| `GET /api/trading/history` | — | Agrégats ou trade_ledger.jsonl | Courbe PnL 30 jours {date, pnl, trades, win_rate} | [OBSERVÉ] |

### Routes Costs

| Endpoint | Cache TTL | Données lues | Retourne | Tag |
|----------|-----------|-------------|----------|-----|
| `GET /api/costs/summary` | 5 min | token_costs.jsonl | today, month, by_agent {today, month, total, model} | [OBSERVÉ] |
| `GET /api/costs/history` | 15 min | Agrégats ou token_costs.jsonl | 30 jours historique {date, cost} | [OBSERVÉ] |

### Routes Content

| Endpoint | Cache TTL | Données lues | Retourne | Tag |
|----------|-----------|-------------|----------|-----|
| `GET /api/content/summary` | 2 min | drafts.json, logs mtimes, publish_history.json, agents/memory/ | scrapers status, drafts (total/pending/approved), published (today/recent) | [OBSERVÉ] |
| `GET /api/content/history` | 15 min | Agrégats ou publish_history.json | 30 jours publications {date, published} | [OBSERVÉ] |

### Routes Polymarket

| Endpoint | Cache TTL | Données lues | Retourne | Tag |
|----------|-----------|-------------|----------|-----|
| `GET /api/polymarket/live` | 30s | POLY_FACTORY/state/ (risk, accounts, trades) | global_status, capital, pnl, positions, strategies, recent_trades | [OBSERVÉ] |
| `GET /api/polymarket/strategies` | 60s | POLY_FACTORY/state/accounts/, registry/ | Par stratégie : mode, capital, pnl, win_rate, sharpe, promotion_status | [OBSERVÉ] |
| `GET /api/polymarket/trades` | 60s | paper_trades_log.jsonl, live_trades_log.jsonl | Trades paginés (?mode, ?strategy, ?limit, ?offset) | [OBSERVÉ] |
| `GET /api/polymarket/health` | 30s | heartbeat, bus, feeds | orchestrator, pending_events, dead_letter, agents, signal_freshness | [OBSERVÉ] |

### Routes Documentation

| Endpoint | Cache TTL | Données lues | Retourne | Tag |
|----------|-----------|-------------|----------|-----|
| `GET /api/docs` | — | Liste statique de 5 docs .md | {id, label, available} | [OBSERVÉ] |
| `GET /api/docs/:id` | — | Fichier .md sur disque | {id, label, content} (markdown brut) | [OBSERVÉ] |

---

## Frontend (React + Vite)

### Pages

| Page | Composant | Endpoints consommés | Refresh | Affichage principal | Tag |
|------|-----------|-------------------|---------|-------------------|-----|
| Vue Globale | Overview.jsx | health, trading, tradingPerf, costs, content, tradingHistory, tradingTrades, polyLive | 30-120s | Kill switch banner, 8 métriques clés, PnL 7j, agents, POLY risk | [OBSERVÉ] |
| System Map | SystemMap.jsx | health | 30s | DAG pipeline, topologie 70+ agents, interconnexions | [OBSERVÉ] |
| Trading | Trading.jsx | trading, tradingPerf, tradingTrades, tradingHistory | 20-120s | Capital, performances, positions, trades, agents, risque | [OBSERVÉ] |
| Polymarket | Polymarket.jsx | polyLive, polyStrategies, polyTrades, polyHealth | 30-60s | Stratégies, leaderboard, equity curve, drawdown, promotion gate | [OBSERVÉ] |
| Content | Content.jsx | content | 60s | Pipeline, scrapers, drafts, agents runtime | [OBSERVÉ] |
| Coûts LLM | Costs.jsx | costs | 60s | Coûts par agent/modèle, pie chart, historique | [OBSERVÉ] |
| Infrastructure | Infrastructure.jsx | health, storage | 30-60s | Disque, pollers, ressources, watchdog | [OBSERVÉ] |
| Docs | Docs.jsx | docs | On-demand | Viewer markdown (architecture, bundles) | [OBSERVÉ] |

### Client API

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Base URL | `/api` (relatif, proxié par nginx) | [OBSERVÉ] |
| Auth | `x-api-key` depuis localStorage (`openclaw_api_key`) | [OBSERVÉ] |
| Polling | Hook `useApiData(fetchFn, intervalMs)` avec {data, error, loading, refresh} | [OBSERVÉ] |
| Formatage | `fmt()`, `fmtUSD()`, `fmtPct()`, `timeAgo()` | [OBSERVÉ] |

---

## Sécurité

### Authentification

| Aspect | Statut | Tag |
|--------|--------|-----|
| Mécanisme | `x-api-key` header → comparaison avec `DASHBOARD_API_KEY` (.env) | [OBSERVÉ] |
| Clé stockée côté client | localStorage (`openclaw_api_key`) | [OBSERVÉ] |
| Rotation de clé | Aucun mécanisme automatique | [OBSERVÉ] |
| Rate limiting | **Aucun** | [OBSERVÉ] |
| HTTPS | **Non** — nginx écoute sur port 80 (HTTP) | [OBSERVÉ] |

### Exposition réseau

| Aspect | Statut | Tag |
|--------|--------|-----|
| Express | localhost:3001 (non exposé directement) | [OBSERVÉ] |
| nginx | IPv6 `[2a02:4780:7:c72f::1]:80` | [OBSERVÉ] |
| Headers sécurité nginx | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` | [OBSERVÉ] |
| Timeouts nginx | connect 5s, read 10s | [OBSERVÉ] |

### Données sensibles

| Donnée | Exposée ? | Tag |
|--------|-----------|-----|
| API key dashboard | Dans .env (600 perms, OK) | [OBSERVÉ] |
| Wallet addresses | Via /api/polymarket/live (si données dans accounts) | [DÉDUIT] |
| Positions ouvertes | Oui, via /api/trading/live | [OBSERVÉ] |
| Historique PnL | Oui, via /api/trading/performance | [OBSERVÉ] |

---

## Variables d'environnement

| Variable | Rôle | Tag |
|----------|------|-----|
| `DASHBOARD_API_KEY` | Clé authentification API | [OBSERVÉ] |
| `ALLOWED_ORIGIN` | CORS origin (Vercel + IP locale) | [OBSERVÉ] |
| `PORT` | Port Express (défaut 3001) | [OBSERVÉ] |
| `STATE_DIR` | Chemin state trading | [OBSERVÉ] |
| `WORKSPACE_DIR` | Racine workspace | [OBSERVÉ] |
| `AGGREGATES_DIR` | Chemin agrégats | [OBSERVÉ] |
| `POLY_BASE_PATH` | Racine state POLY_FACTORY | [OBSERVÉ] |

---

## Risques

### R-01 : Pas de HTTPS

**Sévérité** : ÉLEVÉ

Le dashboard est servi en HTTP (port 80). La clé API transite en clair. Tout intermédiaire réseau peut intercepter le `x-api-key` header et accéder aux données de trading. [OBSERVÉ]

### R-02 : Pas de rate limiting

**Sévérité** : MOYEN

Aucune limitation de débit. Un attaquant peut brute-forcer la clé API ou saturer le serveur de requêtes. [OBSERVÉ]

### R-03 : Clé API statique sans rotation

**Sévérité** : MOYEN

La clé est un hash statique dans .env. Pas de mécanisme de rotation, pas d'expiration. [OBSERVÉ]

### R-04 : Lecture directe de fichiers VPS

**Sévérité** : FAIBLE

Le dashboard lit les fichiers d'état directement (readFileSync/readFile). Un path traversal dans un endpoint pourrait exposer d'autres fichiers. Les routes actuelles utilisent des chemins codés en dur (pas d'injection), mais `/api/docs/:id` valide l'ID contre une whitelist. [DÉDUIT]

---

## Recommandations

| # | Action | Priorité |
|---|--------|----------|
| 1 | Activer HTTPS (Let's Encrypt + certbot) | P1 |
| 2 | Ajouter rate limiting (express-rate-limit, 60 req/min) | P2 |
| 3 | Implémenter rotation de clé API (nouveau endpoint ou script) | P3 |
| 4 | Ajouter health check endpoint sans auth (/api/ping) pour monitoring externe | P3 |
