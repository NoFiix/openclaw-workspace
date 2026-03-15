# triggers_cron.md — Déclencheurs et cron jobs Content Factory

**Date** : 2026-03-15
**Source** : `crontab -l` (snapshot dans `99_appendices/crontab.txt`) + code source

---

## Cron jobs Content Factory

| # | Schedule | Script | Contexte | Log | Tag |
|---|----------|--------|----------|-----|-----|
| T-01 | `0 7-23 * * *` | `hourly_scraper.js` | Docker exec | `state/hourly_scraper.log` | [OBSERVÉ] |
| T-02 | `15 19 * * *` | `scraper.js` | Docker exec | `state/daily_scraper.log` | [OBSERVÉ] |
| T-03 | `@reboot +35s` | `poller.js` (content) | Docker exec -d (daemon) | `state/content_poller.log` (dans container) | [OBSERVÉ] |

### Commandes exactes

**T-01 — hourly_scraper.js**
```bash
0 7-23 * * * docker exec openclaw-openclaw-gateway-1 node /home/node/.openclaw/workspace/skills_custom/hourly_scraper.js >> /home/openclawadmin/openclaw/workspace/state/hourly_scraper.log 2>&1
```
- **Fréquence** : 17 fois/jour (7h-23h UTC, toutes les heures pile)
- **Durée estimée** : 20-30s par exécution [DÉDUIT]
- **Log** : append dans `state/hourly_scraper.log` (sur l'hôte)

**T-02 — scraper.js**
```bash
15 19 * * * docker exec openclaw-openclaw-gateway-1 node /home/node/.openclaw/workspace/skills_custom/scraper.js >> /home/openclawadmin/openclaw/workspace/state/daily_scraper.log 2>&1
```
- **Fréquence** : 1 fois/jour à 19:15 UTC
- **Durée estimée** : 10-15s + N × 200ms (traductions Haiku) [DÉDUIT]
- **Log** : append dans `state/daily_scraper.log` (sur l'hôte)

**T-03 — poller.js (content)**
```bash
@reboot sleep 35 && docker exec -d openclaw-openclaw-gateway-1 sh -c 'node /home/node/.openclaw/workspace/skills_custom/poller.js >> /home/node/.openclaw/workspace/state/content_poller.log 2>&1'
```
- **Fréquence** : lance au boot, tourne en continu (polling 2s)
- **Note** : `docker exec -d` = détaché — PAS de supervision de processus [OBSERVÉ]
- **Log** : `state/content_poller.log` DANS le container Docker [OBSERVÉ]

---

## Autres déclencheurs (non-cron)

| # | Script | Déclencheur | Fréquence | Tag |
|---|--------|-------------|-----------|-----|
| T-04 | `cleanup.js` | Recipe YAML (dimanche 3h) | Hebdomadaire | [DÉDUIT] d'après RETENTION.md |
| T-05 | `youtube_analyzer.js` | [INCONNU] — via agents/analyst schedule? | Daily/Weekly/Monthly | [SUPPOSÉ] |
| T-06 | `router.js` | Importé comme module (pas standalone) | On-demand | [OBSERVÉ] |
| T-07 | `drafts.js` | Importé par hourly_scraper.js + poller.js | On-demand | [OBSERVÉ] |
| T-08 | `pending.js` | Importé par scraper.js + poller.js | On-demand | [OBSERVÉ] |
| T-09 | `twitter.js` | Importé par poller.js | On-demand | [OBSERVÉ] |

---

## Logs associés

| Log | Emplacement | Rotation | Taille estimée | Tag |
|-----|-------------|----------|---------------|-----|
| `hourly_scraper.log` | `workspace/state/` (hôte) | Aucune visible | ~500 Ko/mois [DÉDUIT] | [OBSERVÉ] |
| `daily_scraper.log` | `workspace/state/` (hôte) | Aucune visible | ~50 Ko/mois [DÉDUIT] | [OBSERVÉ] |
| `content_poller.log` | Container Docker `/home/node/.openclaw/workspace/state/` | Aucune visible | [INCONNU] taille | [OBSERVÉ] |
| `router-log.jsonl` | `workspace/state/` | **Aucune** — append-only illimité | Croissance continue | [OBSERVÉ] |
| `content_publish_history.json` | Container Docker `state/` | Auto-prune 200 entrées / 30 jours | ~50-200 Ko | [OBSERVÉ] |
| `cleanup-log.jsonl` | `state/` | [INCONNU] | [INCONNU] | [DÉDUIT] |

---

## Conflits potentiels avec d'autres systèmes

### CONFLIT C-04 : hourly_scraper vs scraper (chevauchement RSS)

**Observation** [OBSERVÉ] : `hourly_scraper.js` et `scraper.js` accèdent aux mêmes 6 flux RSS.
- `hourly_scraper.js` utilise `seen_articles.json` comme cache de dedup
- `scraper.js` utilise la dedup par titre (60 premiers chars)
- Les deux utilisent des mécanismes de dedup **différents et non partagés**

**Impact** : FAIBLE — pas de conflit fonctionnel, mais un article peut être traité par les deux systèmes indépendamment (1 tweet horaire + 1 dans la liste quotidienne). C'est probablement le comportement voulu.

**Sévérité** : LOW

### CONFLIT C-05 : poller.js content vs poller.js trading (confusion)

**Observation** [OBSERVÉ] :
- `skills_custom/poller.js` = content poller (Telegram, drafts)
- `skills_custom/trading/poller.js` = trading poller (agents JS trading)
- Noms identiques, chemins différents

**Impact** : Confusion possible lors du debug. Pas de conflit technique car ils tournent dans des processus séparés.

**Sévérité** : LOW

### CONFLIT C-06 : content_poller.log dans le container

**Observation** [OBSERVÉ] : Le log du content poller est écrit DANS le container Docker (`/home/node/.openclaw/workspace/state/content_poller.log`) via `docker exec -d`. Si le container est recréé, ce log est perdu.

**Impact** : Perte de logs de debug. Les volumes Docker peuvent monter le workspace, mais la persistance n'est pas garantie sans vérification.

**Sévérité** : MEDIUM

---

## Chronogramme journalier type

```
UTC  Événement
───  ──────────────────────────────────────────
00   (rien content — bus_cleanup trading à 02-03h)
...
07   hourly_scraper.js → 1 draft Telegram
08   hourly_scraper.js → 1 draft Telegram
     youtube_analyzer → rapport daily [SUPPOSÉ]
09   hourly_scraper.js → 1 draft Telegram
...
19   hourly_scraper.js → 1 draft Telegram
19:15 scraper.js → liste 20 articles Telegram
     Daniel sélectionne "1,3,5" → poller.js génère drafts
...
23   hourly_scraper.js → dernier draft du jour
     (poller.js tourne en continu, traite les boutons)
```
