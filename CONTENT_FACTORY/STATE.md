# CONTENT_FACTORY/STATE.md — Sources de vérité

> Fichiers d'état Content dans `state/` à la racine (pas dans CONTENT_FACTORY/).

---

## FICHIERS CRITIQUES

| Fichier | Écrit par | Vérité | Notes |
|---------|-----------|--------|-------|
| `state/content_publish_history.json` | `poller.js` | ✅ Publications | Filtrer par `ts >= todayStart` (epoch), pas string |
| `state/drafts.json` | `poller.js`, `hourly_scraper.js` | ✅ Drafts actifs | IDs #1-100, TTL 24h |
| `state/waiting_selection.json` | `scraper.js` | ✅ Articles en attente | |
| `state/poller_offset.json` | `poller.js` | Offset Telegram | Reprise après crash |
| `state/seen_articles.json` | `hourly_scraper.js` | Dédup hourly | ⚠️ dédup séparé de scraper.js |
| `state/content_poller.log` | `poller.js` | Log debug | Jamais source de vérité |
| `state/hourly_scraper.log` | `hourly_scraper.js` | Log debug | |

**Fichiers inconnus (ne pas supprimer) :** `telegram_offset.json` | `pending_jobs.json` | `approvals.jsonl`

---

## SOURCES RSS (6)

CoinTelegraph, CoinDesk, The Block, Decrypt (EN→FR) + Cryptoast, JournalDuCoin (FR)

---

## HIÉRARCHIE DES SOURCES

1. `state/content_publish_history.json` → publications réelles
2. `state/drafts.json` → drafts actifs
3. `state/waiting_selection.json` → articles en attente
4. Logs → debug uniquement
