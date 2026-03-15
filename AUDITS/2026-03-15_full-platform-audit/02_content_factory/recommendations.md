# recommendations.md — Recommandations Content Factory

**Date** : 2026-03-15
**Priorité** : Quick wins → Corrections critiques → Harmonisation future

---

## Quick wins (< 1h chacun)

### QW-01 : Ajouter le content poller à PM2

**Problème** : R-01 — poller.js lancé via `@reboot docker exec -d`, pas supervisé.
**Action** : Ajouter `content-poller` dans `ecosystem.config.cjs` avec autorestart.
**Effort** : 15 min
**Impact** : Élimine le risque de crash silencieux du pipeline de publication.
**Priorité** : **P1**

### QW-02 : Ajouter rotation de router-log.jsonl dans cleanup.js

**Problème** : R-03 + R-11 — append-only sans purge.
**Action** : Ajouter une entrée dans `cleanup.js` : `state/router-log.jsonl → 30 jours`.
**Effort** : 10 min
**Impact** : Empêche la croissance illimitée du fichier.
**Priorité** : **P3**

### QW-03 : Rediriger le log content_poller vers l'hôte

**Problème** : R-04 — log dans le container, perdu au recreate.
**Action** : Modifier le `@reboot` cron pour écrire sur l'hôte :
```bash
@reboot sleep 35 && docker exec -d openclaw-openclaw-gateway-1 sh -c 'node ... >> /home/node/.openclaw/workspace/state/content_poller.log 2>&1'
```
Le path `/home/node/.openclaw/workspace/` est monté en volume → déjà persisté sur l'hôte. Vérifier que le volume mount est bien en place.
**Effort** : 10 min
**Impact** : Logs persistent indépendamment du lifecycle du container.
**Priorité** : **P2**

### QW-04 : Extraire les sources RSS dans un fichier de config

**Problème** : R-10 — 6 sources hardcodées dans 2 fichiers différents.
**Action** : Créer `references/rss_sources.json` avec la liste, importé par les deux scripts.
**Effort** : 30 min
**Impact** : Source unique de vérité, maintenance simplifiée.
**Priorité** : **P3**

---

## Corrections critiques

### CC-01 : Implémenter le token tracking LLM

**Problème** : R-02 — coûts LLM Content Factory invisibles.
**Action** : Patcher `hourly_scraper.js`, `scraper.js`, et `poller.js` pour appeler `logTokens()` après chaque appel Claude. Le module `logTokens.js` existe déjà dans le trading pipeline.
**Effort** : 2-3h
**Impact** : Visibilité complète des coûts LLM. Nécessaire pour le dashboard et l'optimisation budgétaire.
**Priorité** : **P1**

### CC-02 : Externaliser les modèles LLM dans une config

**Problème** : R-08 — identifiants de modèles hardcodés.
**Action** : Créer `references/content_models.json` :
```json
{
  "selection": "claude-haiku-4-5-20251001",
  "translation": "claude-haiku-4-5-20251001",
  "writing": "claude-sonnet-4-6",
  "writing_hourly": "claude-sonnet-4-6"
}
```
**Effort** : 1h
**Impact** : Migration de modèle sans toucher au code. Facilite l'A/B testing de modèles.
**Priorité** : **P2**

### CC-03 : Étendre seen_articles.json à 72h

**Problème** : R-06 — dedup 24h insuffisante pour les articles qui restent longtemps dans les feeds RSS.
**Action** : Changer `SEEN_TTL_MS` de 24h à 72h dans `hourly_scraper.js`.
**Effort** : 5 min
**Impact** : Réduit significativement les doublons proposés.
**Priorité** : **P3**

---

## Harmonisation future avec TRADING_FACTORY et POLY_FACTORY

### H-01 : Unifier le monitoring content + trading dans SYSTEM_WATCHDOG

**Situation actuelle** :
- SYSTEM_WATCHDOG (JS, cron */15min) surveille le trading poller + kill switch
- Le content poller n'a [INCONNU] surveillance spécifique

**Recommandation** : Ajouter un health check du content poller dans SYSTEM_WATCHDOG :
- Vérifier que `state/drafts.json` est récent (< 2h pendant les heures actives 7h-23h)
- Vérifier que `state/poller_offset.json` avance (offset croissant)
- Alerter Telegram si le poller semble mort

**Effort** : 2-4h
**Priorité** : **P2**

### H-02 : Aligner la structure agents/ entre Content et Trading

**Situation actuelle** :
- Content agents : `agents/scraper/`, `agents/copywriter/`, etc. (lowercase, AGENTS.md + SOUL.md)
- Trading JS agents : `skills_custom/trading/KILL_SWITCH_GUARDIAN/`, etc. (UPPERCASE, handler.js)
- POLY_FACTORY agents : `POLY_FACTORY/agents/poly_*.py` (Python, classes)

3 conventions différentes dans le même workspace.

**Recommandation** : Documenter les conventions dans un fichier partagé. Ne pas migrer (trop risqué), mais clarifier la frontière dans la documentation.

**Effort** : 1h (documentation)
**Priorité** : **P4**

### H-03 : News scoring partagé entre Content et Trading

**Situation actuelle** :
- Content Factory : `scraper.js` collecte les news pour publication
- Trading Factory : `NEWS_SCORING` (agents/news_scoring) score les news pour le trading
- POLY_FACTORY : `PolyNewsStrat` consomme des signaux news pour les prediction markets

Trois systèmes collectent et analysent les news indépendamment.

**Recommandation** : Évaluer la possibilité d'un flux partagé : RSS → scoring unique → consumer content + consumer trading. Risque : couplage excessif.

**Effort** : Investigation 2h, implémentation 1-2 jours
**Priorité** : **P4** (après stabilisation des trois systèmes)

### H-04 : Content Factory V2 — validation avant lancement

**Situation actuelle** : La V2 (10 agents, 3 couches) est documentée dans CONTEXT_BUNDLE_CONTENT mais marquée 🔲.

**Recommandation** : Avant de lancer la V2, s'assurer que :
1. Token tracking est implémenté (CC-01) pour mesurer le coût de la V1
2. Le content poller est sous PM2 (QW-01) pour la stabilité
3. Les KPIs V1 sont mesurés (taux de publication, engagement Twitter)
4. Budget LLM V2 estimé (10 agents × N appels/jour)

**Priorité** : **P3** (prérequis avant V2)

---

## Résumé des priorités

| Priorité | Action | Effort | Impact |
|----------|--------|--------|--------|
| **P1** | QW-01 : Content poller sous PM2 | 15 min | Stabilité publication |
| **P1** | CC-01 : Token tracking LLM | 2-3h | Visibilité coûts |
| **P2** | QW-03 : Log poller vers hôte | 10 min | Persistance logs |
| **P2** | CC-02 : Externaliser modèles LLM | 1h | Maintenance simplifiée |
| **P2** | H-01 : Monitoring content dans watchdog | 2-4h | Détection pannes |
| **P3** | QW-02 : Rotation router-log.jsonl | 10 min | Hygiène fichiers |
| **P3** | QW-04 : RSS sources en config | 30 min | Source unique de vérité |
| **P3** | CC-03 : Dedup 72h | 5 min | Moins de doublons |
| **P3** | H-04 : Prérequis V2 | — | Préparation stratégique |
| **P4** | H-02 : Documentation conventions | 1h | Clarté |
| **P4** | H-03 : News scoring partagé | 1-2 jours | Déduplication effort |
