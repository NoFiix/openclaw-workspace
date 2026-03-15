# shared_architecture.md — Architecture Transverse OpenClaw

**Date** : 2026-03-15
**Scope** : Vue d'ensemble des composants partagés, interactions inter-systèmes, observabilité

---

## Résumé exécutif

OpenClaw est composé de **3 systèmes indépendants** (Content, Trading, POLY) qui partagent **4 composants transverses** : SYSTEM_WATCHDOG (monitoring), GLOBAL_TOKEN_TRACKER/ANALYST (coûts LLM), Telegram (alertes/publications), et le Dashboard (visualisation). Ces systèmes coexistent sur un VPS unique sans coordination directe. Le principal risque architectural est l'absence de supervision du superviseur (watchdog non monitoré). [OBSERVÉ/DÉDUIT]

---

## Diagramme d'architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        VPS srv1425899                                │
│                   Ubuntu 22.04 · 8 Go RAM · 97 Go                   │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │  Content Factory  │  │  Trading Factory  │  │   POLY_FACTORY    │  │
│  │     (Docker)      │  │     (Docker)      │  │      (PM2)        │  │
│  │                   │  │                   │  │                   │  │
│  │ hourly_scraper    │  │ trading/poller    │  │ poly-orchestrator │  │
│  │ scraper           │  │ 24 agents JS      │  │ 19 agents Python  │  │
│  │ poller (daemon)   │  │ bus JSONL (170Mo)  │  │ bus JSONL (10Mo)  │  │
│  │ drafts/pending    │  │ state/trading/     │  │ state/bus/        │  │
│  │ twitter           │  │                   │  │ state/accounts/   │  │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  │
│           │                      │                      │            │
│  ─────────┴──────────────────────┴──────────────────────┴────────    │
│                    COMPOSANTS TRANSVERSES                             │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    SYSTEM_WATCHDOG                            │    │
│  │            Cron */15 · Docker exec · Node.js                  │    │
│  │  Surveille: 21 agents trading + content scripts + POLY       │    │
│  │  Alertes: Telegram CRIT/WARN · Rapport 08h UTC               │    │
│  │  ⚠️ NON SUPERVISÉ LUI-MÊME                                   │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │              TOKEN TRACKING (LLM Costs)                       │    │
│  │  Trading: logTokens.js → token_costs.jsonl ✅                 │    │
│  │  POLY: poly_log_tokens.py → token_costs.jsonl ⚠️ (vide)      │    │
│  │  Content: ❌ NON TRACKÉ (~30% des coûts)                      │    │
│  │  → GLOBAL_TOKEN_TRACKER (horaire) → GLOBAL_TOKEN_ANALYST (IA) │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    TELEGRAM (4 bots)                           │    │
│  │  BUILDER → Content drafts/publications (3 scripts)            │    │
│  │  TRADER  → P&L, trades, kills, tokens, news (8 agents)       │    │
│  │  SYSTEM  → Alertes CRIT/WARN + rapport 08h (watchdog)        │    │
│  │  POLY    → Reports POLY, paper trades (publisher)             │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │              DASHBOARD (Express + React)                       │    │
│  │  Backend: Express 3001 (localhost) · 17 endpoints · x-api-key │    │
│  │  Frontend: React/Vite · 8 pages · nginx reverse proxy         │    │
│  │  Lit: state/trading/ + POLY_FACTORY/state/ + logs + disk      │    │
│  │  ⚠️ HTTP seulement (pas de TLS)                               │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────┐                                            │
│  │      nginx :80       │ → reverse proxy → dashboard-api :3001      │
│  │   (IPv6 public)      │ → static files → dashboard/web/dist       │
│  └──────────────────────┘                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Interactions inter-systèmes

### Flux de données croisés

| Source | Destination | Donnée | Mécanisme | Tag |
|--------|------------|--------|-----------|-----|
| Trading agents | GLOBAL_TOKEN_TRACKER | Coûts LLM | logTokens.js → token_costs.jsonl | [OBSERVÉ] |
| POLY agents | GLOBAL_TOKEN_TRACKER | Coûts LLM | poly_log_tokens.py → token_costs.jsonl | [OBSERVÉ] |
| Content scripts | — | **Aucun tracking** | — | [OBSERVÉ] |
| SYSTEM_WATCHDOG | Telegram SYSTEM | Alertes | sendMessage API | [OBSERVÉ] |
| Trading agents | Telegram TRADER | Reports, trades, kills | sendMessage API | [OBSERVÉ] |
| Content scripts | Telegram BUILDER | Drafts, publications | sendMessage/sendPhoto API | [OBSERVÉ] |
| POLY publisher | Telegram POLY | Reports, paper trades | sendMessage API | [OBSERVÉ] |
| Tous les state/ | Dashboard API | Lecture fichiers | fs.readFile (polling) | [OBSERVÉ] |

### Ce qui n'est PAS connecté

| Système A | Système B | Interaction manquante | Impact | Tag |
|-----------|-----------|---------------------|--------|-----|
| Trading Factory | POLY_FACTORY | Pas de bus partagé, pas de signaux croisés | Deux systèmes de trading indépendants (C-03) | [OBSERVÉ] |
| Content Factory | Token Tracker | Pas de logTokens dans scripts content | ~30% coûts LLM invisibles | [OBSERVÉ] |
| NEWS_SCORING (JS) | POLY news_strat (Python) | Bridge `news:high_impact` non implémenté | Stratégie POLY zombie (C-12) | [OBSERVÉ] |
| SYSTEM_WATCHDOG | Lui-même | Pas d'auto-monitoring | SPOF critique | [OBSERVÉ] |

---

## Variables d'environnement transverses

### Par système

| Système | Fichier env | Variables clés | Tag |
|---------|------------|---------------|-----|
| Content | Container Docker (.env) | ANTHROPIC_API_KEY, BUILDER_TELEGRAM_*, TWITTER_*, CRYPTORIZON_CHANNEL_ID | [OBSERVÉ] |
| Trading | Container Docker (.env) | ANTHROPIC_API_KEY, TRADER_TELEGRAM_*, BINANCE_API_KEY | [OBSERVÉ] |
| POLY | POLY_FACTORY/.env | POLYMARKET_*, WALLET_PRIVATE_KEY, BINANCE_API_*, ANTHROPIC_API_KEY, POLY_TELEGRAM_* | [OBSERVÉ] |
| Dashboard | dashboard/api/.env | DASHBOARD_API_KEY, ALLOWED_ORIGIN, *_DIR paths | [OBSERVÉ] |
| Watchdog | Container Docker (.env) | TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID | [OBSERVÉ] |

### Clés partagées entre systèmes

| Clé | Systèmes utilisateurs | Risque si révoquée | Tag |
|-----|----------------------|-------------------|-----|
| ANTHROPIC_API_KEY | Content + Trading + POLY (3 .env distincts, possiblement même clé) | Tous les LLM calls échouent | [DÉDUIT] |
| BINANCE_API_KEY | Trading + POLY (2 .env distincts) | Feeds prix down | [DÉDUIT] |

---

## Schedulers et synchronisation

### Comparaison des schedulers

| Propriété | Content | Trading | POLY | Tag |
|-----------|---------|---------|------|-----|
| Scheduler | Cron (host) | Poller.js (boucle ~1s) | run_orchestrator.py (boucle 2s) | [OBSERVÉ] |
| Exécution | Docker exec | Docker exec | PM2 direct | [OBSERVÉ] |
| Supervision | `@reboot` cron (daemon poller) | `@reboot` cron + watchdog | PM2 restart + heartbeat | [OBSERVÉ] |
| Bus | Fichiers plats (state/*.json) | JSONL (state/trading/bus/) | JSONL (state/bus/) | [OBSERVÉ] |
| Agents | 3 scripts + 4 modules | 24 agents (schedule.json) | 19 agents (orchestrator tick) | [OBSERVÉ] |

### Timeline journalière

```
00:00 ─────────────────────────────────────────────────────── 23:59
  │
  02:00  bus_cleanup_trading.js
  03:00  bus_rotation.js
  03:30  bus_cleanup_trading.js (doublon C-08)
  │
  07:00  hourly_scraper.js ── toutes les heures ── 23:00
  │      │
  08:00  SYSTEM_WATCHDOG rapport quotidien
  08:00  GLOBAL_TOKEN_ANALYST (Lun + Jeu)
  │
  */15   SYSTEM_WATCHDOG checks
  │
  ~1s    Trading poller (continu)
  ~2s    POLY orchestrator (continu)
  ~2s    Content poller Telegram (continu)
  │
  19:15  scraper.js quotidien
  │
  20:00  GLOBAL_TOKEN_TRACKER rapport
  20:00  POLY_TRADING_PUBLISHER rapport
```

---

## Observabilité

### Couverture du monitoring

| Composant | Monitoring | Alertes | Dashboard | Tag |
|-----------|-----------|---------|-----------|-----|
| Trading agents (21) | SYSTEM_WATCHDOG (stale detection) | Telegram CRIT/WARN | ✅ Health page | [OBSERVÉ] |
| Content scripts (3) | SYSTEM_WATCHDOG (log mtime) | Telegram WARN | ✅ Content page | [OBSERVÉ] |
| POLY agents (19) | POLY_HEARTBEAT + SYSTEM_WATCHDOG | Telegram + bus event | ✅ Polymarket page | [OBSERVÉ] |
| Dashboard API | PM2 (process) | PM2 restart | ❌ Pas de self-check | [OBSERVÉ] |
| SYSTEM_WATCHDOG | **Rien** | **Aucune** | ❌ | [OBSERVÉ] |
| Infrastructure (disque) | SYSTEM_WATCHDOG | Telegram WARN/CRIT | ✅ Infrastructure page | [OBSERVÉ] |
| Coûts LLM | GLOBAL_TOKEN_TRACKER | Telegram rapport | ✅ Costs page (partiel) | [OBSERVÉ] |
| Backups | **Rien** | **Aucune** | ❌ | [OBSERVÉ] |

### Métriques non couvertes

| Métrique | Impact | Tag |
|----------|--------|-----|
| CPU par processus | poly-orchestrator à 98% non détecté | [DÉDUIT] |
| RAM par processus | Fuite mémoire non détectable | [DÉDUIT] |
| Latence API dashboard | Dégradation non mesurée | [DÉDUIT] |
| Taux d'erreur API | Erreurs HTTP non comptées | [DÉDUIT] |
| Freshness feeds POLY | binance_raw.json mtime non vérifié | [OBSERVÉ] |
| Coûts Content Factory | ~$0.30-0.50/jour invisibles | [OBSERVÉ] |

---

## SPOFs architecturaux

| # | SPOF | Composants impactés | Mitigation existante | Tag |
|---|------|-------------------|---------------------|-----|
| 1 | **VPS unique** | TOUT | Aucune | [OBSERVÉ] |
| 2 | **SYSTEM_WATCHDOG** | Tout le monitoring | Aucune (pas supervisé) | [OBSERVÉ] |
| 3 | **Disque /dev/sda1** | Data + backups | Alertes disk % seulement | [OBSERVÉ] |
| 4 | **Anthropic API key** | 3 systèmes LLM | Aucune redondance | [DÉDUIT] |
| 5 | **Container Docker** | Content + Trading poller | Watchdog check PID | [OBSERVÉ] |
| 6 | **nginx** | Dashboard accès externe | Aucune | [OBSERVÉ] |

---

## Synthèse des risques transverses

| Rang | Risque | Sévérité | Source |
|------|--------|----------|--------|
| 1 | Clés privées world-readable (POLY .env 664) | CRITIQUE | infrastructure_security.md R-01 |
| 2 | Dashboard HTTP sans TLS | ÉLEVÉ | dashboard.md R-01, infrastructure_security.md R-02 |
| 3 | Watchdog non supervisé (SPOF monitoring) | ÉLEVÉ | watchdog.md SPOF |
| 4 | Backups stales (12j) et locaux (même disque) | ÉLEVÉ | infrastructure_security.md R-05 |
| 5 | Ports Docker exposés sans firewall | ÉLEVÉ | infrastructure_security.md R-03/R-04 |
| 6 | Coûts Content Factory non trackés (~30%) | MOYEN | token_monitoring.md #1 |
| 7 | Canal TRADER surchargé (8 émetteurs) | MOYEN | telegram_bots.md R-01 |
| 8 | poller.log 48 Mo sans rotation | MOYEN | infrastructure_security.md R-06 |
| 9 | cleanup.js non schedulé | MOYEN | shared_scripts.md R-01 |
| 10 | router.js orphelin | FAIBLE | shared_scripts.md R-02 |

---

## Recommandations prioritaires (top 10 transverses)

| # | Action | Priorité | Effort |
|---|--------|----------|--------|
| 1 | `chmod 600 POLY_FACTORY/.env` | P0 | 1 min |
| 2 | Activer UFW (22, 80 only) | P0 | 15 min |
| 3 | HTTPS via Let's Encrypt | P1 | 30 min |
| 4 | Backup quotidien automatisé + offsite | P1 | 2h |
| 5 | Watchdog-du-watchdog (cron externe vérifiant heartbeat) | P1 | 15 min |
| 6 | logTokens() dans Content Factory | P1 | 1h |
| 7 | Rotation poller.log (logrotate) | P1 | 15 min |
| 8 | Rate limiting dashboard API | P2 | 30 min |
| 9 | Scheduler cleanup.js | P2 | 15 min |
| 10 | Séparer alertes CRIT dans canal Telegram dédié | P2 | 30 min |
