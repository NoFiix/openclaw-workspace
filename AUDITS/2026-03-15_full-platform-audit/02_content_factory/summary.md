# summary.md — Content Factory

**Date** : 2026-03-15
**Scope** : Pipeline de création de contenu automatisé pour @CryptoRizon

---

## Mission du système

Pipeline automatisé de veille crypto, curation, rédaction et publication de contenu pour la communauté **@CryptoRizon** (~20k membres). Le système découvre des articles via RSS, les propose à Daniel via Telegram, génère des tweets dans un style éditorial précis (Ogilvy/Halbert), et publie sur Twitter/X + Telegram après validation humaine.

---

## Entrée principale / Sortie principale

| Direction | Description | Tag |
|-----------|-------------|-----|
| **Entrée** | 6 flux RSS crypto (CoinTelegraph, CoinDesk, Bitcoin Magazine, The Defiant, Cryptoast, JournalDuCoin) | [OBSERVÉ] |
| **Sortie** | Tweets publiés sur @CryptoRizon (Twitter/X) + canal Telegram CryptoRizon | [OBSERVÉ] |
| **Entrée secondaire** | YouTube Data API v3 (analyse concurrentielle, 6 chaînes) | [OBSERVÉ] |
| **Sortie secondaire** | Rapports analytiques daily/weekly/monthly dans `agents/analyst/reports/` | [OBSERVÉ] |

---

## Fréquence d'exécution

| Composant | Fréquence | Déclencheur | Tag |
|-----------|-----------|-------------|-----|
| hourly_scraper.js | Toutes les heures, 7h-23h UTC | Cron | [OBSERVÉ] |
| scraper.js | 1×/jour à 19:15 UTC | Cron | [OBSERVÉ] |
| poller.js (content) | Continu (polling Telegram 2s) | @reboot cron (Docker) | [OBSERVÉ] |
| cleanup.js | Hebdomadaire (dimanche 3h) | Cron/recipe | [DÉDUIT] |
| youtube_analyzer.js | Daily/weekly/monthly | [INCONNU] déclencheur exact | [SUPPOSÉ] |

---

## Statut actuel

**ACTIF — Pipeline V1 opérationnel** [OBSERVÉ]

| Sous-système | Statut | Tag |
|-------------|--------|-----|
| Scraping RSS (6 sources) | ACTIF | [OBSERVÉ] — cron vérifié |
| Traduction EN→FR (Haiku) | ACTIF | [OBSERVÉ] — dans scraper.js |
| Sélection d'articles (Haiku) | ACTIF | [OBSERVÉ] — dans hourly_scraper.js |
| Rédaction tweets (Sonnet) | ACTIF | [OBSERVÉ] — dans poller.js + hourly_scraper.js |
| Gestion drafts (Telegram) | ACTIF | [OBSERVÉ] — drafts.js + poller.js |
| Publication Twitter | ACTIF | [OBSERVÉ] — twitter.js OAuth 1.0a |
| Publication Telegram canal | ACTIF | [OBSERVÉ] — dans poller.js |
| YouTube Analytics | ACTIF | [OBSERVÉ] — youtube_analyzer.js + agents/analyst |
| Content Factory V2 (10 agents) | NON DÉPLOYÉ | [OBSERVÉ] — CONTEXT_BUNDLE_CONTENT.md roadmap 🔲 |

---

## Points de fragilité

| # | Fragilité | Sévérité | Tag |
|---|-----------|----------|-----|
| F-01 | `poller.js` est un singleton long-running sans supervision PM2 — lancé via `@reboot` cron `docker exec -d`, pas de restart automatique en cas de crash | ÉLEVÉ | [OBSERVÉ] |
| F-02 | `state/router-log.jsonl` en append-only sans rotation ni purge — croissance illimitée | MOYEN | [OBSERVÉ] |
| F-03 | RSS fetch séquentiel (pas parallèle) — 6 sources × ~5s = ~30s par cycle | FAIBLE | [OBSERVÉ] |
| F-04 | Aucun health check sur le content poller — crash silencieux possible | ÉLEVÉ | [DÉDUIT] |
| F-05 | Credentials Twitter hardcodés en env vars dans le container Docker — pas de rotation visible | MOYEN | [SUPPOSÉ] |
| F-06 | `seen_articles.json` déduplication sur 24h seulement — republication possible si même article resurface après 24h | FAIBLE | [OBSERVÉ] |
| F-07 | Token tracking non implémenté pour les LLM calls du content pipeline — coûts invisibles | MOYEN | [OBSERVÉ] — roadmap CONTEXT_BUNDLE "🔲 Token tracking" |
