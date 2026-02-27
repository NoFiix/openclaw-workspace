# RETENTION.md - Politique de rétention des mémoires

## Règles par durée

### 7 jours (purge automatique)
- URLs scrapées (scraper/memory/)
- News envoyées à Daniel (scraper/memory/)
- Publications Twitter (publisher/memory/)
- Erreurs API (publisher/memory/)

### 10 jours (purge automatique)
- Posts rédigés (copywriter/memory/)

### 30 jours (purge automatique)
- Erreurs sources inaccessibles (scraper/memory/)
- Emails traités — résumé 1 ligne (email/memory/)

### Jusqu'à action de Daniel (purge manuelle)
- Drafts email en attente de validation (email/memory/drafts/)

### 90 jours (purge automatique)
- Améliorations proposées par builder (builder/memory/)

### Permanent (jamais supprimé)
- agents/copywriter/preferences.md
- agents/email/preferences.md
- agents/builder/preferences.md
- intel/DAILY-INTEL.md (écrasé chaque jour, pas supprimé)

## Purge automatique
Un cron hebdomadaire tourne chaque dimanche à 3h du matin.
Il supprime les fichiers memory/ selon les règles ci-dessus.
Script : workspace/skills_custom/cleanup.js
