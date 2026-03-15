# dependency_map.md — Cartographie des dépendances inter-systèmes

**Date** : 2026-03-15
**Scope** : Toutes les dépendances entre les 3 systèmes + 4 composants partagés

---

## Résumé exécutif

L'environnement OpenClaw comprend **3 systèmes de production** (Content, Trading, POLY) et **4 composants transverses** (Watchdog, Token Tracker, Telegram, Dashboard). Les systèmes sont **largement indépendants** — aucun bus partagé, aucun state mutualisé en écriture. Les dépendances sont quasi-exclusivement en **lecture seule** (dashboard, watchdog) ou via **Telegram** (notifications). Le couplage le plus fort est entre Trading Factory et POLY_FACTORY via `POLY_TRADING_PUBLISHER` et `GLOBAL_TOKEN_TRACKER` qui lisent directement les fichiers state POLY. [OBSERVÉ]

---

## Matrice de dépendances

### Systèmes entre eux

| Système A | Système B | Type | Fichiers partagés | Risque collision | Criticité | Tag |
|-----------|-----------|------|-------------------|-----------------|-----------|-----|
| TRADING_FACTORY | POLY_FACTORY | Lecture croisée | POLY_TRADING_PUBLISHER (JS) lit `POLY_FACTORY/state/accounts/`, `trading/paper_trades_log.jsonl`, `registry/` | Aucun (lecture seule) | MOYEN | [OBSERVÉ] |
| TRADING_FACTORY | POLY_FACTORY | Lecture croisée | GLOBAL_TOKEN_TRACKER (JS) lit `POLY_FACTORY/state/llm/token_costs.jsonl` | Aucun (lecture seule) | FAIBLE | [OBSERVÉ] |
| TRADING_FACTORY | POLY_FACTORY | Aucune coordination | Pas de bus partagé, pas de signaux croisés, pas de risk partagé | N/A | FAIBLE | [OBSERVÉ] |
| TRADING_FACTORY | CONTENT_FACTORY | Indépendants | Aucun fichier partagé direct | N/A | FAIBLE | [OBSERVÉ] |
| TRADING_FACTORY | CONTENT_FACTORY | Même container Docker | Scripts des deux systèmes exécutés dans `openclaw-gateway-1` | Crash container = les deux down | FORT | [OBSERVÉ] |
| TRADING_FACTORY | CONTENT_FACTORY | Même crontab | Cron host lance les scripts des deux systèmes | Erreur crontab = les deux down | MOYEN | [OBSERVÉ] |
| POLY_FACTORY | CONTENT_FACTORY | Indépendants | Aucune dépendance détectée | N/A | FAIBLE | [OBSERVÉ] |
| TRADING_FACTORY | POLY_FACTORY | Même Binance API | Les deux utilisent `api.binance.com` (clés potentiellement différentes) | Rate limiting partagé | MOYEN | [DÉDUIT] |
| TRADING_FACTORY | POLY_FACTORY | news:high_impact bridge manquant | NEWS_SCORING (JS) → POLY news_strat (Python) — prévu mais non implémenté (C-12) | N/A | MOYEN | [OBSERVÉ] |

### Systèmes ↔ Dashboard

| Système | Dashboard | Type | Données lues | Risque collision | Criticité | Tag |
|---------|-----------|------|-------------|-----------------|-----------|-----|
| TRADING_FACTORY | Dashboard API | Lecture | `state/trading/` (schedules, memory, exec, bus, learning, risk) | Aucun | FAIBLE | [OBSERVÉ] |
| POLY_FACTORY | Dashboard API | Lecture | `POLY_FACTORY/state/` (accounts, bus, registry, feeds, orchestrator) | Aucun | FAIBLE | [OBSERVÉ] |
| CONTENT_FACTORY | Dashboard API | Lecture | `state/drafts.json`, logs mtimes, `content_publish_history.json`, `agents/*/memory/` | Aucun | FAIBLE | [OBSERVÉ] |
| Infrastructure | Dashboard API | Lecture | `df -h`, `du`, log sizes | Aucun | FAIBLE | [OBSERVÉ] |

### Systèmes ↔ SYSTEM_WATCHDOG

| Système | Watchdog | Type | Données lues | Risque collision | Criticité | Tag |
|---------|----------|------|-------------|-----------------|-----------|-----|
| TRADING_FACTORY | SYSTEM_WATCHDOG | Lecture | `state/trading/schedules/*.schedule.json`, `poller.log` mtime, `killswitch.json` | Aucun | FAIBLE | [OBSERVÉ] |
| POLY_FACTORY | SYSTEM_WATCHDOG | Lecture | `heartbeat_state.json`, `global_risk_state.json`, `paper_trades_log.jsonl`, accounts | Aucun | FAIBLE | [OBSERVÉ] |
| POLY_FACTORY | SYSTEM_WATCHDOG | Process check | `pgrep -f run_orchestrator.py` | Aucun | FAIBLE | [OBSERVÉ] |
| CONTENT_FACTORY | SYSTEM_WATCHDOG | Lecture | `hourly_scraper.log` mtime, `daily_scraper.log` mtime | Aucun | FAIBLE | [OBSERVÉ] |
| CONTENT_FACTORY | SYSTEM_WATCHDOG | Process check | PID content poller dans Docker | Aucun | FAIBLE | [OBSERVÉ] |
| Docker | SYSTEM_WATCHDOG | Process check | `docker inspect` gateway container | Aucun | FAIBLE | [OBSERVÉ] |

### Systèmes ↔ Token Tracker

| Système | Token Tracker | Type | Fichier | Risque | Criticité | Tag |
|---------|--------------|------|---------|--------|-----------|-----|
| TRADING_FACTORY | GLOBAL_TOKEN_TRACKER | Écriture → Lecture | Agents JS écrivent `state/learning/token_costs.jsonl`, Tracker lit | Aucun (append-only) | FAIBLE | [OBSERVÉ] |
| POLY_FACTORY | GLOBAL_TOKEN_TRACKER | Écriture → Lecture | `poly_log_tokens.py` écrit `POLY_FACTORY/state/llm/token_costs.jsonl`, Tracker lit | Aucun (append-only, actuellement vide) | FAIBLE | [OBSERVÉ] |
| CONTENT_FACTORY | GLOBAL_TOKEN_TRACKER | **Aucune connexion** | Content ne logge pas ses tokens LLM | N/A — ~30% coûts invisibles | MOYEN | [OBSERVÉ] |

### Systèmes ↔ Telegram

| Système | Bot Telegram | Chat ID | Émetteurs | Criticité | Tag |
|---------|-------------|---------|-----------|-----------|-----|
| CONTENT_FACTORY | BUILDER_TELEGRAM_BOT_TOKEN | BUILDER_TELEGRAM_CHAT_ID | hourly_scraper, scraper, poller, drafts (4 scripts) | MOYEN | [OBSERVÉ] |
| TRADING_FACTORY | TRADER_TELEGRAM_BOT_TOKEN | TRADER_TELEGRAM_CHAT_ID | TRADING_PUBLISHER, TOKEN_TRACKER, TOKEN_ANALYST, KILL_SWITCH, GATEKEEPER, ORCHESTRATOR, NEWS_SCORING, TUNER (8 agents) | MOYEN | [OBSERVÉ] |
| SYSTEM_WATCHDOG | TELEGRAM_BOT_TOKEN | TELEGRAM_CHAT_ID | SYSTEM_WATCHDOG (1 émetteur) | MOYEN | [OBSERVÉ] |
| POLY_FACTORY | POLY_TELEGRAM_BOT_TOKEN | POLY_TELEGRAM_CHAT_ID | POLY_TRADING_PUBLISHER (1 émetteur) | FAIBLE | [OBSERVÉ] |

**DÉCOUVERTE CRITIQUE** : Les 4 CHAT_ID pointent vers le **même canal Telegram** (même valeur). Tous les messages (drafts, P&L, alertes CRIT, reports POLY) arrivent dans un seul chat. [OBSERVÉ]

---

## Schéma ASCII global

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VPS srv1425899                                   │
│                                                                          │
│  ┌─────────────────────┐      ┌─────────────────────┐                    │
│  │   CONTENT FACTORY    │      │   TRADING FACTORY    │                   │
│  │      (Docker)        │      │      (Docker)        │                   │
│  │                      │      │                      │                   │
│  │  hourly_scraper ─┐   │      │  24 agents JS ──┐    │                   │
│  │  scraper ────────┤   │      │  poller.js ──────┤    │                   │
│  │  poller (daemon) ┤   │      │  bus JSONL 170Mo ┤    │                   │
│  │  drafts/pending ─┘   │      │                  │    │                   │
│  │                      │      │  POLY_TRADING_ ──┼──────────┐            │
│  │  state/drafts.json   │      │  PUBLISHER       │    │     │(lit)       │
│  │  state/*.log         │      │                  │    │     │            │
│  └──────────┬───────────┘      │  GLOBAL_TOKEN_ ──┼────────┐│            │
│             │                  │  TRACKER         │    │   ││(lit)       │
│             │                  │                  │    │   ││            │
│             │                  │  state/trading/  │    │   ││            │
│             │                  └────────┬─────────┘    │   ││            │
│             │                           │              │   ││            │
│  ┌──────────┼───────────────────────────┼──────────────┼───┼┼──────┐     │
│  │          │  CONTAINER DOCKER         │              │   ││      │     │
│  │          │  openclaw-gateway-1       │              │   ││      │     │
│  │          │  (Content + Trading JS)   │              │   ││      │     │
│  └──────────┼───────────────────────────┼──────────────┼───┼┼──────┘     │
│             │                           │              │   ││            │
│             │                           │              │   ↓↓            │
│             │                  ┌────────┴──────────────┴────┐            │
│             │                  │      POLY_FACTORY           │            │
│             │                  │         (PM2)               │            │
│             │                  │                             │            │
│             │                  │  19 agents Python           │            │
│             │                  │  bus JSONL 10Mo             │            │
│             │                  │  state/accounts/            │            │
│             │                  │  state/llm/token_costs.jsonl│            │
│             │                  └──────────┬──────────────────┘            │
│             │                             │                               │
│  ═══════════╪═════════════════════════════╪═══════════════════════════    │
│             │   COMPOSANTS TRANSVERSES    │                               │
│             │                             │                               │
│  ┌──────────┼─────────────────────────────┼────────────────────────┐     │
│  │  SYSTEM_WATCHDOG (cron */15, lit tout)                          │     │
│  │    lit→ state/trading/schedules/ (Trading)                      │     │
│  │    lit→ POLY_FACTORY/state/heartbeat/ (POLY)                    │     │
│  │    lit→ state/*.log mtimes (Content)                            │     │
│  │    lit→ df, du (Infrastructure)                                 │     │
│  │    ⚠️  NON SUPERVISÉ (heartbeat fix appliqué)                   │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │  DASHBOARD (Express :3001 + React, nginx :80)                   │     │
│  │    lit→ state/trading/ (7 routes)                               │     │
│  │    lit→ POLY_FACTORY/state/ (4 routes)                          │     │
│  │    lit→ state/drafts.json + logs (2 routes)                     │     │
│  │    lit→ df, du (1 route)                                        │     │
│  │    ⚠️  HTTP sans TLS                                            │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │  TELEGRAM (4 bots → 1 seul canal !)                             │     │
│  │    BUILDER: 4 scripts content                                   │     │
│  │    TRADER:  8 agents trading                                    │     │
│  │    SYSTEM:  1 watchdog                                          │     │
│  │    POLY:    1 publisher                                         │     │
│  │    ⚠️  14 émetteurs → 1 chat = bruit                            │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │  TOKEN TRACKER (agrège Trading + POLY, ignore Content)          │     │
│  │    lit→ state/learning/token_costs.jsonl (Trading ✅)            │     │
│  │    lit→ POLY_FACTORY/state/llm/token_costs.jsonl (POLY ⚠️ vide) │     │
│  │    ❌  Content non tracké (~30% invisible)                       │     │
│  └─────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Chaînes de dépendances critiques

### Si le container Docker meurt
```
openclaw-gateway-1 DOWN
  → Content Factory DOWN (hourly_scraper, scraper, poller) [OBSERVÉ]
  → Trading poller DOWN (trading/poller.js) [OBSERVÉ]
  → SYSTEM_WATCHDOG DOWN (exécuté via docker exec) [OBSERVÉ]
  → Token Tracker DOWN (exécuté via trading poller) [DÉDUIT]
  → Telegram alerts DOWN (watchdog + trading agents muets) [DÉDUIT]
  → Dashboard stale (lit des fichiers figés) [DÉDUIT]
  ⚠️ SEUL poly-orchestrator (PM2) et dashboard-api (PM2) survivent [OBSERVÉ]
```

### Si ANTHROPIC_API_KEY est révoquée
```
ANTHROPIC_API_KEY invalid
  → Content: hourly_scraper échoue (Haiku sélection + Sonnet rédaction) [DÉDUIT]
  → Content: scraper échoue (Haiku traduction) [DÉDUIT]
  → Content: poller échoue (Sonnet modifications) [DÉDUIT]
  → Trading: NEWS_SCORING échoue (61% budget LLM) [DÉDUIT]
  → Trading: TRADE_GENERATOR échoue (38% budget LLM) [DÉDUIT]
  → POLY: opp_scorer, no_scanner échouent (Sonnet/Haiku) [DÉDUIT]
  → GLOBAL_TOKEN_ANALYST échoue (Sonnet) [DÉDUIT]
  ⚠️ 7+ composants impactés dans les 3 systèmes [DÉDUIT]
```

### Si Binance API est down
```
Binance API DOWN
  → Trading: BINANCE_PRICE_FEED arrête les prix [OBSERVÉ]
  → Trading: Pipeline entier bloqué (pas de prix = pas de signal) [DÉDUIT]
  → Trading: Kill switch TRIPPED après 5 min exchange down [OBSERVÉ]
  → POLY: PolyBinanceFeed arrête les prix crypto [OBSERVÉ]
  → POLY: Stratégies dépendant des prix crypto bloquées [DÉDUIT]
  ⚠️ 2 systèmes impactés simultanément [DÉDUIT]
```
