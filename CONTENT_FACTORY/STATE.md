# CONTENT_FACTORY/STATE.md — Sources de vérité

> Dernière mise à jour : Mars 2026
> Les fichiers d'état Content sont dans `state/` à la racine (pas dans CONTENT_FACTORY/).

---

## RÈGLE FONDAMENTALE

Les fichiers d'état Content vivent dans `state/` à la racine du workspace.
`state/` ne bouge jamais — c'est la mémoire vivante du système.

---

## FICHIERS D'ÉTAT CRITIQUES

### Publications — source de vérité

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `state/content_publish_history.json` | `poller.js` | Dashboard Content | ✅ OUI — historique publications |

**Structure :**
```json
[
  {
    "id": "...",
    "title": "...",
    "status": "published",
    "ts": 1710000000000,
    "date": "2026-03-21",
    "platform": "twitter"
  }
]
```

**P&L publications :** filtrer par `date` (format `YYYY-MM-DD`) pour les stats "aujourd'hui".
Le filtre utilise le timestamp epoch (`ts >= todayStart`) — pas une comparaison de string.

---

### Drafts — source de vérité

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `state/drafts.json` | `poller.js`, `hourly_scraper.js` (via drafts.js) | `poller.js`, Dashboard | ✅ OUI — drafts actifs |
| `state/draft_counter.json` | `drafts.js` | `drafts.js` | ✅ OUI — compteur ID monotone |
| `state/current_draft.json` | `poller.js` | `poller.js` | OUI — draft en cours d'édition |

**Structure drafts.json :**
```json
{
  "1": {
    "id": 1,
    "title": "...",
    "content": "...",
    "source": "...",
    "created_at": "...",
    "ttl": "...",
    "status": "pending"
  }
}
```

**Règles drafts :**
- IDs #1 à #100 (rotation circulaire)
- TTL 24h — expirés automatiquement
- Partagé entre `poller.js` et `hourly_scraper.js` via `drafts.js`

---

### Sélection en attente

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `state/waiting_selection.json` | `scraper.js` (via pending.js) | `poller.js` (via pending.js) | ✅ OUI — articles en attente sélection |

Contient les articles présentés à Dan via Telegram, en attente de sélection manuelle.

---

### État du poller

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `state/poller_offset.json` | `poller.js` | `poller.js` | OUI — offset Telegram getUpdates |

Permet au poller de reprendre là où il s'est arrêté après un crash.

---

### Déduplication

| Fichier | Écrit par | Lu par | Source de vérité |
|---------|-----------|--------|-----------------|
| `state/seen_articles.json` | `hourly_scraper.js` | `hourly_scraper.js` | OUI — articles déjà vus |

⚠️ `scraper.js` a son propre mécanisme de déduplication séparé.
Deux mécanismes coexistent sur les mêmes sources RSS — fonctionnel mais incohérent.

---

### Fichiers inconnus / usage non confirmé

| Fichier | Statut |
|---------|--------|
| `state/telegram_offset.json` | Usage inconnu — possiblement legacy |
| `state/pending_jobs.json` | Usage inconnu |
| `state/approvals.jsonl` | Usage inconnu |

Ne pas supprimer ces fichiers sans avoir identifié leur usage exact.

---

### Logs (debug uniquement)

| Fichier | Écrit par | Lu par | Nature |
|---------|-----------|--------|--------|
| `state/content_poller.log` | `poller.js` (stdout redirect) | Dashboard health | Log (debug) |
| `state/hourly_scraper.log` | `hourly_scraper.js` (stdout redirect) | Dashboard health, storage | Log (debug) |
| `state/daily_scraper.log` | `scraper.js` (stdout redirect) | Dashboard content | Log (debug) |

⚠️ Ces fichiers sont des **logs**, pas des sources de vérité.
Ne jamais les utiliser pour calculer des métriques métier.

---

## 6 SOURCES RSS SCRAPÉES

Les deux scrapers (hourly + daily) utilisent les mêmes 6 sources :

| Source | Langue | Fréquence |
|--------|--------|-----------|
| CoinTelegraph | EN → FR | Hourly + Daily |
| CoinDesk | EN → FR | Hourly + Daily |
| The Block | EN → FR | Hourly + Daily |
| Decrypt | EN → FR | Hourly + Daily |
| Cryptoast | FR | Hourly + Daily |
| JournalDuCoin | FR | Hourly + Daily |

---

## HIÉRARCHIE DES SOURCES — CONTENT

Pour une même métrique, priorité décroissante :

1. `state/content_publish_history.json` → publications réelles (source de vérité)
2. `state/drafts.json` → drafts actifs
3. `state/waiting_selection.json` → articles en attente
4. `state/content_poller.log` → debug uniquement

---

## DASHBOARD — CE QUE LIT L'API

Le dashboard `content.js` lit :

| Métrique dashboard | Source réelle |
|-------------------|---------------|
| Posts publiés aujourd'hui | `state/content_publish_history.json` filtré par timestamp today |
| Posts annulés | `state/content_publish_history.json` filtré par status "cancelled" |
| Drafts total | `state/drafts.json` |
| Santé poller | `state/content_poller.log` (dernière ligne) |
| Santé hourly scraper | `state/hourly_scraper.log` (dernière ligne) |

**⚠️ Token tracking absent :** les coûts LLM Content ne sont pas dans
`state/trading/learning/token_costs.jsonl`. Les 3 scripts (poller, hourly_scraper,
scraper) n'appellent pas `logTokens()`. ~30% des coûts LLM de la plateforme
sont invisibles dans le dashboard LLM Costs.
