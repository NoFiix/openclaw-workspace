# pipeline_flows.md — Flux du pipeline Content Factory

**Date** : 2026-03-15
**Méthode** : lecture du code source (skills_custom/*.js) + crontab + agents/*.md

---

## Pipeline complet

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FLUX HORAIRE                                │
│                    (7h-23h UTC, cron horaire)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [ENTRÉE] 6 flux RSS crypto                                       │
│      │                                                              │
│      ▼                                                              │
│  hourly_scraper.js                                                  │
│      ├─ Fetch 6 RSS (séquentiel, 10 items/source, max 60)         │
│      ├─ Filtre : seen_articles.json (dedup 24h)                    │
│      ├─ Filtre fenêtre temporelle : 2h → 4h → all                 │
│      ├─ Haiku sélectionne le meilleur article                      │
│      ├─ Fetch body article + og:image                              │
│      ├─ Sonnet rédige tweet (500 chars max, style CryptoRizon)     │
│      ├─ Mark URL as seen                                           │
│      ├─ drafts.js: createDraft(content, "hourly", image, url)      │
│      └─ drafts.js: sendDraft(id) → Telegram Builder chat           │
│             │                                                       │
│             ▼                                                       │
│  [ATTENTE] Daniel voit le draft dans Telegram                      │
│      │                                                              │
│      ├─ [✅ Publish] → twitter.js → Tweet + Canal Telegram         │
│      ├─ [✏️ Modify]  → Sonnet modifie → nouveau draft affiché     │
│      ├─ [🖼 Image]   → re-fetch og:image alternative              │
│      └─ [❌ Cancel]  → suppression draft                           │
│                                                                     │
│  [SORTIE] Tweet publié sur @CryptoRizon + canal Telegram          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        FLUX QUOTIDIEN                               │
│                    (19:15 UTC, cron daily)                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [ENTRÉE] 6 flux RSS crypto                                       │
│      │                                                              │
│      ▼                                                              │
│  scraper.js                                                         │
│      ├─ Fetch 6 RSS (séquentiel, 10/source, max 20 après dedup)   │
│      ├─ Traduction EN→FR (Haiku, séquentiel, 200ms throttle)      │
│      ├─ Save → intel/DAILY-INTEL.md + intel/data/YYYY-MM-DD.json  │
│      ├─ pending.js: saveWaitingSelection(articles)                  │
│      └─ Telegram: liste numérotée "1. Titre | 2. Titre | ..."     │
│             │                                                       │
│             ▼                                                       │
│  [ATTENTE] Daniel répond avec "1,3,5"                              │
│      │                                                              │
│      ▼                                                              │
│  poller.js (détecte isSelectionMessage)                             │
│      ├─ pending.js: getSelectedArticles("1,3,5")                    │
│      ├─ Sonnet génère le post (1500 tokens, style Ogilvy/Halbert)  │
│      ├─ drafts.js: createDraft(content, "daily")                   │
│      ├─ drafts.js: sendDraft(id) → Telegram avec boutons          │
│      └─ pending.js: clearWaitingSelection()                         │
│             │                                                       │
│             ▼                                                       │
│  [MÊME BOUCLE] Publish / Modify / Image / Cancel                  │
│                                                                     │
│  [SORTIE] Tweet(s) publiés sur @CryptoRizon                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     SERVICES SUPPORT                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  poller.js (long-running daemon)                                   │
│      ├─ Poll Telegram getUpdates toutes les 2s                     │
│      ├─ Gère les callback_query (boutons)                          │
│      ├─ Gère les messages texte (sélection, modification)          │
│      ├─ Gère les photos (ajout image au draft)                     │
│      └─ Persiste offset dans state/poller_offset.json              │
│                                                                     │
│  youtube_analyzer.js                                               │
│      ├─ 6 chaînes YouTube (3 FR, 3 EN)                            │
│      ├─ 2 keywords recherchés par run                              │
│      └─ → agents/analyst/reports/daily/YYYY-MM-DD.json             │
│                                                                     │
│  cleanup.js (dimanche 3h)                                          │
│      └─ Purge mémoire agents selon RETENTION.md                    │
│         (scraper 7j, publisher 7j, copywriter 10j, email 30j,     │
│          builder 90j, intel/data 7j)                               │
│                                                                     │
│  router.js (utilitaire, pas standalone)                            │
│      └─ Scoring task → routage vers modèle optimal                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Ordre d'exécution des agents

### Flux horaire (17 exécutions/jour)

```
1. [CRON 0 7-23] hourly_scraper.js
2.   └→ Fetch RSS (6 sources, séquentiel)
3.   └→ Filtre dedup (seen_articles.json)
4.   └→ Haiku sélection (1 appel LLM)
5.   └→ Fetch body + image
6.   └→ Sonnet rédaction (1 appel LLM)
7.   └→ createDraft + sendDraft (Telegram)
8. [HUMAIN] Daniel valide/modifie/annule
9.   └→ [Publish] twitter.js → Tweet + Canal
```

### Flux quotidien (1 exécution/jour)

```
1. [CRON 15 19] scraper.js
2.   └→ Fetch RSS (6 sources, séquentiel)
3.   └→ Dedup + trier par date
4.   └→ Haiku traduction EN→FR (N appels, throttled 200ms)
5.   └→ Save DAILY-INTEL.md + data JSON
6.   └→ Telegram : liste numérotée
7. [HUMAIN] Daniel répond "1,3,5"
8. [CONTINU] poller.js détecte la sélection
9.   └→ getSelectedArticles
10.  └→ Sonnet génère le post (1 appel LLM)
11.  └→ createDraft + sendDraft
12. [HUMAIN] Daniel valide/modifie
13.  └→ [Publish] twitter.js → Tweet
```

---

## Conditions de passage entre étapes

| Transition | Condition | Tag |
|-----------|-----------|-----|
| RSS → Sélection | Articles non vus (dedup 24h) ET fenêtre temporelle OK | [OBSERVÉ] |
| Sélection → Rédaction | Haiku retourne un index valide | [OBSERVÉ] |
| Rédaction → Draft | Sonnet retourne du contenu non-vide | [OBSERVÉ] |
| Draft → Publication | Daniel clique "✅ Publish" dans Telegram | [OBSERVÉ] |
| Draft → Modification | Daniel clique "✏️ Modify" + envoie instructions | [OBSERVÉ] |
| Scraper → Sélection humaine | Articles sauvés dans waiting_selection.json (TTL 20h) | [OBSERVÉ] |
| Sélection humaine → Draft | Daniel envoie des numéros (regex `/^[\d\s,]+$/`) | [OBSERVÉ] |

---

## Points de blocage potentiels

| # | Point de blocage | Impact | Tag |
|---|-----------------|--------|-----|
| B-01 | **Validation humaine obligatoire** — aucun tweet ne s'auto-publie | Pipeline bloqué si Daniel ne répond pas | [OBSERVÉ] |
| B-02 | **API Claude down** — Haiku ou Sonnet indisponible | Sélection/rédaction impossible, fallback limité (Haiku→premier article) | [OBSERVÉ] |
| B-03 | **Twitter API down** — OAuth échoue | Publication impossible, draft préservé pour retry manuel | [OBSERVÉ] |
| B-04 | **RSS feeds tous down** — 6 sources indisponibles | Aucun article à proposer ; chaque feed échoue indépendamment | [OBSERVÉ] |
| B-05 | **poller.js crash** — pas de supervision PM2 | Tous les callbacks Telegram ignorés, aucune publication possible | [DÉDUIT] |
| B-06 | **waiting_selection.json expiré** — Daniel ne répond pas dans les 20h | Sélection perdue, scraper doit re-runner | [OBSERVÉ] |

---

## Où les données entrent et sortent

### Entrées

```
[EXTERNE]
  ├─ 6 RSS feeds (CoinTelegraph, CoinDesk, Bitcoin Magazine, The Defiant, Cryptoast, JournalDuCoin)
  ├─ YouTube Data API v3 (6 chaînes, 6 keywords)
  ├─ Telegram getUpdates (messages Daniel)
  └─ Article URLs (fetch body + og:image)

[LLM]
  ├─ Anthropic API → claude-haiku-4-5 (sélection, traduction)
  └─ Anthropic API → claude-sonnet-4-6 (rédaction, modification)
```

### Sorties

```
[PUBLICATION]
  ├─ Twitter API v2 → @CryptoRizon (tweets + images)
  └─ Telegram Bot API → canal CryptoRizon + Builder chat

[STATE]
  ├─ state/drafts.json (drafts actifs, TTL 24h)
  ├─ state/seen_articles.json (dedup cache 24h)
  ├─ state/waiting_selection.json (sélection en attente, TTL 20h)
  ├─ state/poller_offset.json (offset Telegram)
  ├─ state/content_publish_history.json (historique publications, 200 entrées max)
  ├─ state/router-log.jsonl (log routage modèle, append-only)
  ├─ intel/DAILY-INTEL.md (liste quotidienne)
  └─ intel/data/YYYY-MM-DD.json (données brutes)

[AGENTS MEMORY]
  ├─ agents/publisher/memory/YYYY-MM-DD.md (log publications)
  ├─ agents/analyst/reports/daily/YYYY-MM-DD.json (rapports YouTube)
  └─ agents/analyst/references/top_performers.json (top vidéos)
```
