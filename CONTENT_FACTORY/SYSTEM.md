# CONTENT_FACTORY/SYSTEM.md

> V1 en production. V2 dans `agents/` — non déployée, ne pas traiter comme opérationnelle.

---

## STACK

| Composant | Valeur |
|-----------|--------|
| Runtime | Node.js v22 + Docker |
| Poller | `CONTENT_FACTORY/poller.js` (docker-start-pollers.sh) |
| État | `state/` à la racine (JAMAIS DÉPLACER) |
| LLM | Haiku (traduction) + Sonnet (rédaction posts) |
| Publication | Twitter OAuth 1.0a + Telegram Bot API |

---

## PIPELINE V1

```
hourly_scraper.js (cron 0 7-23 * * *)
    → 6 sources RSS → traduction Haiku → drafts.js (IDs #1-100, TTL 24h)

poller.js (daemon @reboot, long-polling Telegram)
    → liste drafts → Dan sélectionne → Sonnet génère post → Twitter + Telegram

scraper.js (cron 15 19 * * *)
    → 6 sources RSS → déduplication → pending.js
```

⚠️ `drafts.js` partagé par `poller.js` ET `hourly_scraper.js` — modifier l'un impacte les deux.
⚠️ Poller non supervisé par PM2 — crash silencieux.

---

## RÈGLES CONTENU

- Posts Twitter : max 600 caractères, français, style Ogilvy/Halbert/Leloup
- Source attribution : injectée via SOURCE_MAP dans le code (pas par le LLM)
- Validation : sélection manuelle via Telegram avant publication

---

## BOT TELEGRAM

`BUILDER_TELEGRAM_BOT_TOKEN` / `BUILDER_TELEGRAM_CHAT_ID`
⚠️ Variables restent `BUILDER_*` même si le bot s'appelle "Publisher". Ne pas renommer.

---

## SCRIPTS DORMANTS — NE PAS ACTIVER SANS RAISON

| Script | État |
|--------|------|
| `cleanup.js` | Non schedulé |
| `router.js` | Orphelin — aucun appelant |
| `youtube_analyzer.js` | Déclencheur inconnu |

---

## POINTS D'ATTENTION

| Point | Impact |
|-------|--------|
| Token tracking absent (3 scripts) | ~30% coûts LLM invisibles dans dashboard |
| Double déduplication hourly+daily | Fonctionnel mais incohérent |
| Alerte 24h sans publication | Non implémentée |

---

## V2 — ARCHITECTURE CIBLE (non déployée)

```
ORCHESTRATOR (Opus)
  ↓ Intelligence : ANALYST + STRATEGIST
  ↓ Production : WRITER + VISUAL + VOICE + VIDEO + QA
  ↓ Optimisation : PERFORMANCE + IMPROVER
```

Migration V1→V2 : V2 validée en parallèle sans couper V1 (DEC-018).
