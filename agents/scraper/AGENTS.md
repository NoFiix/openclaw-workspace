# AGENTS.md - Agent Scraper

## Démarrage
1. Lire SOUL.md
2. Lire memory/ (dernière session)
3. Charger les sources depuis recipes/daily_crypto_recap.yaml

## Workflow
1. Scraper toutes les sources
2. Dédupliquer les news (même sujet = 1 seule entrée)
3. Numéroter chaque news
4. Formater en liste lisible
5. Écrire dans intel/DAILY-INTEL.md
6. Écrire les données brutes dans intel/data/YYYY-MM-DD.json
7. Notifier Daniel sur Telegram avec la liste numérotée
8. Logger la session dans memory/YYYY-MM-DD.md

## Format output Telegram
📰 *News Crypto du [date]*

1. [Titre court] — [source]
2. [Titre court] — [source]
...

👉 Réponds avec les numéros qui t'intéressent.

## Gestion des erreurs
- Source inaccessible → continuer avec les autres, signaler à la fin
- Aucune news → signaler à Daniel, ne pas envoyer de liste vide
- Doublon détecté → garder la version la plus complète
