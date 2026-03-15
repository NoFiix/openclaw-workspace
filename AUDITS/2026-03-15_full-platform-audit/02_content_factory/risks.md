# risks.md — Risques Content Factory

**Date** : 2026-03-15
**Méthode** : analyse croisée code source + crontab + agents + state files

---

## Risques identifiés

### CRITIQUE

*Aucun risque critique identifié.* La Content Factory ne gère pas d'argent et a une validation humaine obligatoire avant publication.

---

### ÉLEVÉ

#### R-01 : poller.js sans supervision — crash silencieux

**Description** : Le content poller (`skills_custom/poller.js`) est lancé via `@reboot docker exec -d` (cron). Il n'est PAS supervisé par PM2. En cas de crash (OOM, exception non catchée, restart container), il ne redémarre pas automatiquement.

**Impact** : Toute la boucle de validation (boutons Publish/Modify/Cancel) et la sélection d'articles (réponse "1,3,5") cessent de fonctionner. Daniel envoie des messages qui ne sont jamais traités.

**Détection** : Aucune détection automatique observée. Le SYSTEM_WATCHDOG surveille les processus mais [INCONNU] s'il monitore spécifiquement le content poller dans le container.

**Tag** : [OBSERVÉ] — `@reboot` cron sans restart, pas dans PM2

#### R-02 : aucun token tracking sur les LLM calls content

**Description** : Les appels Claude (Haiku + Sonnet) dans `hourly_scraper.js`, `scraper.js`, et `poller.js` ne tracent pas l'usage de tokens. Aucun `logTokens` n'est appelé.

**Impact** : Coûts LLM invisibles. Avec ~17 appels Sonnet/jour (hourly) + N appels Haiku (traduction) + appels on-demand, les coûts s'accumulent sans monitoring.

**Tag** : [OBSERVÉ] — roadmap CONTEXT_BUNDLE_CONTENT confirme "🔲 Token tracking : Patcher scraper.js + poller.js pour logTokens"

---

### MOYEN

#### R-03 : router-log.jsonl sans rotation

**Description** : `state/router-log.jsonl` est en append-only. Chaque appel à `routeTask()` ajoute une ligne. Aucune rotation ni purge n'est configurée.

**Impact** : Croissance lente mais illimitée. Sur plusieurs mois, le fichier peut atteindre des Mo inutiles.

**Tag** : [OBSERVÉ]

#### R-04 : content_poller.log dans le container Docker

**Description** : Le log du content poller est écrit dans le container Docker. Si le container est recréé (`docker compose up --force-recreate`), le log est perdu.

**Impact** : Perte de traçabilité pour le debug.

**Tag** : [OBSERVÉ] — le `@reboot` cron redirige stdout/stderr vers un path dans le container

#### R-05 : RSS fetch séquentiel sans timeout global

**Description** : Les 6 RSS feeds sont fetchés séquentiellement. Chaque fetch a un timeout de 10s. Si un feed est lent, le cycle total peut prendre 60s+.

**Impact** : Retard dans la publication du draft horaire. Pas bloquant mais dégradation.

**Tag** : [OBSERVÉ]

#### R-06 : seen_articles.json dedup limitée à 24h

**Description** : Le cache de deduplication `seen_articles.json` a un TTL de 24h. Si un article RSS reste dans le feed plus de 24h (fréquent pour les articles populaires), il peut être re-proposé.

**Impact** : Draft en double. Daniel doit identifier manuellement les doublons. Pas critique grâce à la validation humaine.

**Tag** : [OBSERVÉ]

#### R-07 : waiting_selection.json TTL 20h — perte de sélection

**Description** : Si Daniel ne répond pas dans les 20h après le scraper daily, le fichier `waiting_selection.json` expire et est purgé.

**Impact** : Les articles proposés sont perdus. Daniel doit relancer le scraper manuellement.

**Tag** : [OBSERVÉ]

#### R-08 : modèles LLM hardcodés dans le code

**Description** : Les identifiants de modèles (`claude-haiku-4-5-20251001`, `claude-sonnet-4-6`) sont hardcodés dans `hourly_scraper.js` et `poller.js`. Un changement de modèle nécessite de modifier le code source.

**Impact** : Maintenance accrue lors des mises à jour de modèles Anthropic.

**Tag** : [OBSERVÉ]

---

### FAIBLE

#### R-09 : noms de fichiers confusants (poller.js × 2)

**Description** : `skills_custom/poller.js` (content) et `skills_custom/trading/poller.js` (trading) ont le même nom.

**Impact** : Confusion lors du debug ou de la documentation.

**Tag** : [OBSERVÉ]

#### R-10 : sources RSS hardcodées (6 sources)

**Description** : Les 6 sources RSS sont hardcodées dans `hourly_scraper.js` et `scraper.js`. Ajouter/supprimer une source nécessite de modifier 2 fichiers.

**Impact** : Duplication de configuration, risque de divergence entre les deux scripts.

**Tag** : [OBSERVÉ]

#### R-11 : cleanup.js ne purge pas router-log.jsonl

**Description** : Le script `cleanup.js` purge les memory files des agents mais ne touche pas `state/router-log.jsonl`.

**Impact** : Voir R-03 (croissance illimitée).

**Tag** : [DÉDUIT]

---

## Dépendances cachées

| Dépendance | De → Vers | Impact si cassé | Tag |
|-----------|-----------|-----------------|-----|
| `drafts.js` partagé | hourly_scraper + poller → drafts.js | Modification de drafts.js casse les deux pipelines | [OBSERVÉ] |
| `pending.js` partagé | scraper + poller → pending.js | Modification casse le flux de sélection quotidien | [OBSERVÉ] |
| Telegram Bot unique | Tous les scripts content → BUILDER_TELEGRAM_BOT_TOKEN | Révocation du token = tout le content pipeline down | [DÉDUIT] |
| Container Docker | Cron → `docker exec` → scripts JS | Container down = scraper + poller + cleanup down | [OBSERVÉ] |
| ANTHROPIC_API_KEY | hourly_scraper + scraper + poller | Clé invalide/expirée = sélection et rédaction impossibles | [DÉDUIT] |
| Twitter OAuth tokens | poller → twitter.js | 4 tokens (key, secret, access, access_secret) — révocation d'un seul = publication impossible | [DÉDUIT] |

---

## Scripts orphelins potentiels

| Script | Statut | Justification | Tag |
|--------|--------|---------------|-----|
| `router.js` | Semi-orphelin | Exporté comme module mais aucun import trouvé dans les scripts content actifs (hourly_scraper, scraper, poller). Utilisé par le gateway? | [SUPPOSÉ] |
| `router.test.js` | Test unitaire | Test de router.js — utile si router.js est maintenu | [OBSERVÉ] |
| `youtube_analyzer.js` | Actif mais déclencheur [INCONNU] | Pas dans le crontab. Peut-être lancé par l'agent ANALYST via le gateway | [SUPPOSÉ] |

---

## Risques de régression inter-systèmes

| Modification | Système impacté | Risque | Sévérité |
|-------------|----------------|--------|----------|
| Mise à jour container Docker | Content Factory (tous les scripts) | Scripts JS exécutés via `docker exec` — nouvelle image peut casser les paths | ÉLEVÉ |
| Modification de `state/` structure | Content + Trading | Le content poller et le trading poller partagent `workspace/state/` | MOYEN |
| Upgrade Anthropic API / modèles | Content Factory | Modèles hardcodés dans le code — deprecation = erreurs API | MOYEN |
| Modification SYSTEM_WATCHDOG | Content monitoring | Si le watchdog cesse de monitorer le content poller | FAIBLE |
| Modification PM2 ecosystem | Content Factory | Le content poller n'est PAS dans PM2 mais le trading poller l'est — incohérence | FAIBLE |
