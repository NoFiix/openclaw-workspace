# CONTENT_FACTORY/SYSTEM.md — Architecture et fonctionnement

> Dernière mise à jour : Mars 2026
> Voir aussi : `CONTENT_FACTORY/STATE.md` pour les sources de vérité
> Source : CONTEXT_BUNDLE_CONTENT.md + audit Mars 2026 + migration workspace

---

## OBJECTIF

Automatiser la production de contenu crypto pour la marque CryptoRizon.
Publication quotidienne sur Twitter @CryptoRizon et canal Telegram.
Style inspiré Ogilvy / Gary Halbert / Stan Leloup — français exclusivement.

**Statut actuel :** V1 en production — V2 en préparation (non déployée).

---

## STACK TECHNIQUE

| Composant | Technologie |
|-----------|-------------|
| Runtime | Node.js v22 |
| Exécution | Docker container `openclaw-openclaw-gateway-1` |
| Scripts V1 | `CONTENT_FACTORY/` (daemon + crons) |
| Agents V2 | `agents/` (non déployés) |
| État | `state/` à la racine (NE JAMAIS DÉPLACER) |
| LLM | Haiku (traduction, scoring) + Sonnet (rédaction posts) |
| Publication | Twitter OAuth 1.0a + Telegram Bot API |

---

## DEUX COUCHES — NE PAS CONFONDRE

### V1 — EN PRODUCTION (dans `CONTENT_FACTORY/`)

Pipeline simple et stable. C'est ce qui tourne réellement.

```
CONTENT_FACTORY/
├── poller.js          ← daemon Telegram (@reboot)
├── hourly_scraper.js  ← cron 0 7-23 * * *
├── scraper.js         ← cron 15 19 * * *
├── drafts.js          ← module partagé (gestion IDs #1-#100)
├── pending.js         ← module partagé (sélection articles)
├── twitter.js         ← module partagé (publication Twitter)
├── cleanup.js         ← dormant (non schedulé)
├── router.js          ← orphelin (aucun appelant)
└── youtube_analyzer.js← dormant (déclencheur inconnu)
```

### V2 — EN DÉVELOPPEMENT (dans `agents/`)

Architecture 10 agents non encore déployée. Ne pas traiter comme opérationnelle.

```
agents/
├── analyst/
├── strategist/
├── builder/
├── copywriter/
├── email/
├── learner/
├── news_scoring/
├── performance_analyst/
├── publisher/
├── scraper/
└── strategy_tuner/
```

---

## PIPELINE V1 — DÉTAIL

```
hourly_scraper.js (cron 0 7-23 * * * — toutes les heures de 7h à 23h)
    → scrape 6 sources RSS crypto
    → traduction FR via Haiku
    → déduplication
    → stocke dans drafts.js (IDs #1-#100, TTL 24h)
         ↓
poller.js (daemon @reboot — long-polling Telegram)
    → surveille les drafts disponibles
    → envoie liste articles au bot Publisher Telegram
    → Dan sélectionne manuellement via Telegram
    → génère post Twitter via Sonnet (style Ogilvy/Halbert/Leloup)
    → publie sur Twitter (OAuth 1.0a) + Canal Telegram @CryptoRizon
         ↓
scraper.js (cron 15 19 * * * — daily 19h15)
    → 6 sources RSS
    → déduplication
    → traduction FR séquentielle
    → stocke dans pending.js pour sélection
```

**Module partagé critique :** `drafts.js` — utilisé par `poller.js` ET `hourly_scraper.js`.
Si `drafts.js` est modifié, vérifier l'impact sur les deux scripts.

---

## RÈGLES CONTENU

| Règle | Valeur |
|-------|--------|
| Longueur posts Twitter | Max 600 caractères |
| Langue | Français exclusivement |
| Style | Accroche directe, tension narrative, pas de jargon |
| Source attribution | Injectée via SOURCE_MAP dans le code (pas par le LLM) |
| Validation | Sélection manuelle via Telegram avant publication |

---

## BOT TELEGRAM

- **Nom :** Publisher (anciennement Builder)
- **Variables :** `BUILDER_TELEGRAM_BOT_TOKEN` / `BUILDER_TELEGRAM_CHAT_ID`

⚠️ Les variables restent `BUILDER_*` même si le bot s'appelle "Publisher".
Ne pas renommer ces variables d'environnement.

---

## ARCHITECTURE V2 — 10 AGENTS, 3 COUCHES (non déployée)

```
ORCHESTRATOR (Opus — COO, décisions critiques)
        ↓
Couche Intelligence
    ANALYST (Sonnet — veille, data, 0 opinion créative)
    STRATEGIST (Sonnet — angles, concepts, direction créative)
        ↓
Couche Production
    WRITER (Sonnet — copywriter, hook/tension narrative)
    VISUAL (openai-image-gen — miniatures, CTR)
    VOICE (ElevenLabs TTS — voix off)
    VIDEO (ffmpeg — montage, rétention)
    QA (Haiku — auditeur strict, compliance)
        ↓
Couche Optimisation
    PERFORMANCE (métriques post-publication, A/B tests)
    IMPROVER (suggestions continues, workspace/improvements/)
```

**Workflow états V2 :**
```
draft → review → approved → rejected → revision
```

---

## SCRIPTS DORMANTS — NE PAS ACTIVER SANS RAISON

| Script | État | Raison |
|--------|------|--------|
| `cleanup.js` | Dormant — non schedulé | Purge mémoires, à ajouter en cron si nécessaire |
| `router.js` | Orphelin — aucun appelant | Routing modèles IA — non intégré au pipeline |
| `youtube_analyzer.js` | Dormant — déclencheur inconnu | Analyse chaînes YouTube — pas dans crontab ni poller |

---

## DÉMARRAGE ET SUPERVISION

**Le content poller tourne dans Docker** via `docker-start-pollers.sh`.
Il n'est PAS supervisé par PM2 — un crash est silencieux.

```bash
# Vérifier que le poller tourne
docker exec openclaw-openclaw-gateway-1 sh -c "
ps aux | grep 'CONTENT_FACTORY/poller' | grep -v grep
"

# Relancer si crashé
docker exec -d openclaw-openclaw-gateway-1 sh -c "
node /home/node/.openclaw/workspace/CONTENT_FACTORY/poller.js \
  >> /home/node/.openclaw/workspace/state/content_poller.log 2>&1
"

# Vérifier les logs content
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -30 /home/node/.openclaw/workspace/state/content_poller.log
"
```

⚠️ **Alerte recommandée :** ajouter une surveillance si aucune publication
depuis plus de 24h (non encore implémentée).

---

## COÛTS LLM

| Script | Modèle | Usage | Tracking |
|--------|--------|-------|---------|
| `hourly_scraper.js` | Haiku | Traduction FR | ⚠️ Non trackée |
| `poller.js` | Sonnet | Génération posts Twitter | ⚠️ Non trackée |
| `scraper.js` | Haiku | Traduction FR | ⚠️ Non trackée |

**⚠️ Token tracking non implémenté pour Content V1.**
Environ 30% des coûts LLM de la plateforme sont invisibles.
À corriger en patchant les 3 scripts avec `logTokens()`.

---

## ROADMAP V1 → V2

| Phase | Statut |
|-------|--------|
| V1 pipeline (scraper + poller + Twitter + Telegram) | ✅ En production |
| Drafts module (IDs #1-#100, TTL 24h) | ✅ En production |
| Token tracking LLM Content | ❌ Non implémenté |
| V2 architecture 10 agents | 🔲 En développement |
| IMPROVER système (suggestions pending/applied/rejected) | 🔲 En attente V2 |
| YouTube pipeline (script → voix → vidéo → miniature) | 🔲 En attente V2 |
| Shorts/Reels multi-plateforme | 🔲 P7 roadmap |

**Condition migration V1 → V2 :** V2 validée en parallèle sans couper V1.
Ne jamais interrompre V1 avant que V2 soit opérationnelle.

---

## COMMANDES UTILES

```bash
# Dernier post publié
tail -5 ~/openclaw/workspace/state/content_publish_history.json \
  | python3 -m json.tool

# Drafts en attente
cat ~/openclaw/workspace/state/drafts.json \
  | python3 -m json.tool | head -30

# Articles en attente de sélection
cat ~/openclaw/workspace/state/waiting_selection.json \
  | python3 -m json.tool 2>/dev/null || echo "Aucune sélection en attente"

# Logs content poller
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -30 /home/node/.openclaw/workspace/state/content_poller.log
"

# Logs hourly scraper
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -20 /home/node/.openclaw/workspace/state/hourly_scraper.log
"
```

---

## PIÈGES CONNUS

- **Pas de supervision PM2** : un crash du content poller est silencieux — vérifier manuellement si les publications s'arrêtent
- **BUILDER_* variables** : ne pas renommer en PUBLISHER_* — les variables d'env sont `BUILDER_TELEGRAM_BOT_TOKEN` / `BUILDER_TELEGRAM_CHAT_ID`
- **drafts.js partagé** : toute modification impacte poller.js ET hourly_scraper.js
- **router.js orphelin** : ne pas l'intégrer sans comprendre son rôle exact
- **Token tracking absent** : les coûts LLM Content ne sont pas dans le dashboard — ne pas supposer que les coûts affichés sont complets
- **Double déduplication** : hourly_scraper et scraper ont deux mécanismes différents sur les mêmes RSS feeds — fonctionnel mais incohérent
