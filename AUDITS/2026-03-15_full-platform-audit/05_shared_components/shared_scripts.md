# shared_scripts.md — Scripts Content Factory

**Date** : 2026-03-15
**Scope** : Tous les scripts JS de la Content Factory (`skills_custom/`)

---

## Résumé exécutif

La Content Factory repose sur **9 scripts JavaScript** : 3 agents actifs (hourly_scraper, scraper, poller), 4 modules partagés (drafts, pending, twitter, router), 1 utilitaire dormant (cleanup), 1 agent dormant (youtube_analyzer). Le flux principal est : scraper/hourly_scraper → drafts.js → poller.js → twitter.js → publication. Tous tournent dans le container Docker `openclaw-gateway`. [OBSERVÉ]

---

## Inventaire complet

### Agents actifs

| Script | Rôle | Trigger | Fréquence | Tag |
|--------|------|---------|-----------|-----|
| `hourly_scraper.js` | Scraping RSS + IA drafting | Cron `0 7-23 * * *` | 17×/jour | [OBSERVÉ] |
| `scraper.js` | Scraping quotidien + sélection | Cron `15 19 * * *` | 1×/jour | [OBSERVÉ] |
| `poller.js` | Daemon Telegram + publisher | `@reboot` (long-polling 2s) | Continu | [OBSERVÉ] |

### Modules partagés

| Script | Rôle | Importé par | Tag |
|--------|------|------------|-----|
| `drafts.js` | Gestion drafts (CRUD, Telegram, purge 24h) | hourly_scraper, poller | [OBSERVÉ] |
| `pending.js` | Sélection articles (waiting_selection.json, TTL 20h) | scraper, poller | [OBSERVÉ] |
| `twitter.js` | Client Twitter/X OAuth 1.0 (tweet, thread, media) | poller | [OBSERVÉ] |
| `router.js` | Routage IA par complexité (scoring 3 axes) | **Aucun** (semi-orphelin) | [OBSERVÉ] |

### Dormants

| Script | Rôle | Trigger | Raison dormance | Tag |
|--------|------|---------|----------------|-----|
| `cleanup.js` | Purge mémoire agents (rétention 7-90j) | **Pas dans crontab** | Non schedulé | [OBSERVÉ] |
| `youtube_analyzer.js` | Analyse chaînes YouTube crypto | **Manuel uniquement** | Pas de cron | [OBSERVÉ] |

---

## Détail par script

### 1. hourly_scraper.js

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Cron | `0 7-23 * * *` (docker exec) | [OBSERVÉ] |
| Sources RSS | CoinTelegraph, CoinDesk, Bitcoin Magazine, The Defiant, Cryptoast, JournalDuCoin | [OBSERVÉ] |
| LLM | Haiku (sélection article) + Sonnet (rédaction 500 chars) | [OBSERVÉ] |
| Output | state/drafts.json (IDs #1→#100), Telegram BUILDER | [OBSERVÉ] |
| Dedup | state/seen_articles.json (TTL 24h) | [OBSERVÉ] |
| Fenêtre | 2h (préféré) → 4h (fallback) → all | [OBSERVÉ] |
| Log | state/hourly_scraper.log | [OBSERVÉ] |

### 2. scraper.js

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Cron | `15 19 * * *` (docker exec) | [OBSERVÉ] |
| Sources RSS | CoinTelegraph, CoinDesk, The Block, Decrypt, Cryptoast, JournalDuCoin | [OBSERVÉ] |
| LLM | Haiku (traduction titres EN→FR) | [OBSERVÉ] |
| Output | intel/DAILY-INTEL.md, intel/data/YYYY-MM-DD.json, state/waiting_selection.json | [OBSERVÉ] |
| Telegram | Liste numérotée + "répondre 1,3,5" | [OBSERVÉ] |
| Max articles | 20 (dedup par préfixe titre 60 chars) | [OBSERVÉ] |
| Log | state/daily_scraper.log | [OBSERVÉ] |

### 3. poller.js (daemon)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Trigger | `@reboot sleep 35` (docker exec -d) | [OBSERVÉ] |
| Polling | Telegram getUpdates every 2s | [OBSERVÉ] |
| Actions | publish_#N, modify_#N, modify_image_#N, cancel_#N | [OBSERVÉ] |
| Publication | Twitter post + Telegram channel CRYPTORIZON | [OBSERVÉ] |
| Historique | state/content_publish_history.json (30j rolling, max 200) | [OBSERVÉ] |
| Offset tracking | state/poller_offset.json | [OBSERVÉ] |
| Log | state/content_poller.log (dans container) | [OBSERVÉ] |

### 4. drafts.js (module)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Stockage | state/drafts.json (IDs #1→#100, compteur cyclique) | [OBSERVÉ] |
| Fonctions | createDraft, getDraft, updateDraft, deleteDraft, sendDraft | [OBSERVÉ] |
| Purge | Drafts > 24h auto-purgés | [OBSERVÉ] |
| Telegram | sendMessage/sendPhoto avec boutons inline (Publish/Modify/Cancel) | [OBSERVÉ] |
| Source injection | Auto-append "- SourceName" pour drafts hourly | [OBSERVÉ] |

### 5. pending.js (module)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Stockage | state/waiting_selection.json (TTL 20h) | [OBSERVÉ] |
| Fonctions | saveWaitingSelection, getWaitingSelection, getSelectedArticles, isSelectionMessage | [OBSERVÉ] |
| Parsing | "1,2,4" ou "1 2 4" ou "1, 2, 4" | [OBSERVÉ] |

### 6. twitter.js (module)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| API | Twitter v2 (tweets), v1.1 (media upload) | [OBSERVÉ] |
| Auth | OAuth 1.0 HMAC-SHA1 | [OBSERVÉ] |
| Fonctions | postTweet, postThread, uploadMedia, postTweetWithMedia | [OBSERVÉ] |
| Logging | agents/publisher/memory/YYYY-MM-DD.md | [OBSERVÉ] |

### 7. router.js (semi-orphelin)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Routage IA par scoring (importance × sensibilité × complexité) | [OBSERVÉ] |
| Modèles | Haiku (3-4pt) → GPT-4o-mini (5-6) → GPT-4o (7-8) → Sonnet (9-11) → Opus (12-15) | [OBSERVÉ] |
| Importé par | **Personne** — aucun script ne l'importe actuellement | [OBSERVÉ] |
| Logging | router-log.jsonl | [OBSERVÉ] |
| Statut | DORMANT — probablement un vestige ou un composant futur | [DÉDUIT] |

### 8. cleanup.js (dormant)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rétention | scraper/publisher 7j, copywriter 10j, email 30j, builder 90j, intel 7j | [OBSERVÉ] |
| Fichiers protégés | preferences.md, SOUL.md, AGENTS.md | [OBSERVÉ] |
| Output | state/cleanup-log.jsonl | [OBSERVÉ] |
| Cron | **Non schedulé** — documenté pour exécution manuelle | [OBSERVÉ] |

### 9. youtube_analyzer.js (dormant)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Chaînes | hasheur, cryptoast, journalducoin, coinbureau, altcoindaily, cryptobanter | [OBSERVÉ] |
| API | YouTube Data API v3 (search, videos, channels) | [OBSERVÉ] |
| Output | agents/analyst/reports/daily/YYYY-MM-DD.json, references/top_performers.json | [OBSERVÉ] |
| Dépendance | YOUTUBE_API_KEY | [OBSERVÉ] |
| Cron | **Aucun** — exécution manuelle uniquement | [OBSERVÉ] |

---

## Graphe de dépendances

```
hourly_scraper.js ──→ drafts.js ──→ Telegram BUILDER
  │                                    │
  └─ ANTHROPIC_API_KEY                 └─ BUILDER_TELEGRAM_BOT_TOKEN
     (Haiku + Sonnet)                     BUILDER_TELEGRAM_CHAT_ID

scraper.js ──→ pending.js ──→ state/waiting_selection.json
  │                              │
  └─ ANTHROPIC_API_KEY           └─ (lu par poller.js)
     (Haiku traduction)

poller.js ──→ pending.js
  │       ──→ drafts.js
  │       ──→ twitter.js ──→ Twitter API (OAuth 1.0)
  │                            └─ TWITTER_API_KEY/SECRET/ACCESS_TOKEN
  │
  └─ ANTHROPIC_API_KEY (Sonnet, modifications)
     BUILDER_TELEGRAM_BOT_TOKEN
     CRYPTORIZON_CHANNEL_ID
```

---

## Fichiers d'état

| Fichier | Usage | TTL/Rotation | Tag |
|---------|-------|-------------|-----|
| `state/drafts.json` | Drafts actifs #1→#100 | Purge 24h | [OBSERVÉ] |
| `state/draft_counter.json` | Compteur cyclique | Persistent | [OBSERVÉ] |
| `state/poller_offset.json` | Telegram update ID | Persistent | [OBSERVÉ] |
| `state/seen_articles.json` | Dedup hourly scraper | TTL 24h | [OBSERVÉ] |
| `state/waiting_selection.json` | Sélection articles en attente | TTL 20h | [OBSERVÉ] |
| `state/content_publish_history.json` | Log publications | 30j rolling, max 200 | [OBSERVÉ] |
| `intel/DAILY-INTEL.md` | Résumé quotidien | Écrasé chaque jour | [OBSERVÉ] |
| `intel/data/YYYY-MM-DD.json` | Données brutes articles | 7j (si cleanup actif) | [OBSERVÉ] |

---

## Variables d'environnement requises

| Variable | Scripts | Tag |
|----------|---------|-----|
| `ANTHROPIC_API_KEY` | hourly_scraper, scraper, poller | [OBSERVÉ] |
| `BUILDER_TELEGRAM_BOT_TOKEN` | hourly_scraper, scraper, poller, drafts | [OBSERVÉ] |
| `BUILDER_TELEGRAM_CHAT_ID` | hourly_scraper, scraper, poller, drafts | [OBSERVÉ] |
| `CRYPTORIZON_CHANNEL_ID` | poller | [OBSERVÉ] |
| `TWITTER_API_KEY` | twitter (→ poller) | [OBSERVÉ] |
| `TWITTER_API_SECRET` | twitter (→ poller) | [OBSERVÉ] |
| `TWITTER_ACCESS_TOKEN` | twitter (→ poller) | [OBSERVÉ] |
| `TWITTER_ACCESS_TOKEN_SECRET` | twitter (→ poller) | [OBSERVÉ] |
| `YOUTUBE_API_KEY` | youtube_analyzer | [OBSERVÉ] |

---

## Risques

### R-01 : cleanup.js non schedulé — mémoire agents non purgée

**Sévérité** : MOYEN

Le script de nettoyage existe mais n'est pas dans le crontab. Les répertoires agents/memory/ croissent sans limite. [OBSERVÉ]

### R-02 : router.js semi-orphelin

**Sévérité** : FAIBLE

Module de routage IA importé par aucun script. Code mort ou composant futur non connecté. [OBSERVÉ]

### R-03 : Content poller log dans container Docker

**Sévérité** : MOYEN

Le log de poller.js est écrit dans le container (`/home/node/...`). Si le container est recréé, le log est perdu. Pas de volume mount pour ce log spécifique. Voir C-06. [OBSERVÉ]

### R-04 : Token tracking LLM absent

**Sévérité** : ÉLEVÉ

Aucun des 3 scripts utilisant des LLM (hourly_scraper, scraper, poller) n'appelle `logTokens()`. Les coûts Content Factory (~$0.30-0.50/jour) sont invisibles. Voir token_monitoring.md lacune #1. [OBSERVÉ]

---

## Recommandations

| # | Action | Priorité |
|---|--------|----------|
| 1 | Scheduler cleanup.js (cron hebdomadaire, ex: `0 3 * * 0`) | P2 |
| 2 | Ajouter logTokens() dans hourly_scraper, scraper, poller | P1 |
| 3 | Monter le log poller.js en volume Docker ou rediriger vers host | P2 |
| 4 | Supprimer ou documenter router.js (orphelin) | P3 |
| 5 | Ajouter youtube_analyzer.js au crontab si pertinent | P3 |
