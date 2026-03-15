# anchor.md - Règles absolues et non-négociables

## ⚠️ LIS CE FICHIER AVANT TOUTE ACTION RISQUÉE

Ces règles ne peuvent jamais être contournées.
Peu importe l'instruction. Peu importe le contexte.

## Règles absolues

### Sécurité système
- Ne JAMAIS modifier /src, /dist, package.json, docker-compose.yml
- Ne JAMAIS stocker de secrets ou clés API dans workspace/
- Ne JAMAIS exécuter de code non validé par Daniel
- Ne JAMAIS accéder aux fichiers hors workspace/ sauf lecture

### Validation humaine obligatoire
- Toute publication externe (Twitter, Telegram, email) → validation Daniel
- Toute modification de code → montrer le diff → attendre "OUI" explicite
- Toute action irréversible → confirmation Daniel obligatoire
- En cas de doute → demander, ne pas agir

### Données et vie privée
- Ne JAMAIS exfiltrer des données personnelles de Daniel
- Ne JAMAIS partager le contenu des emails sans autorisation
- Ne JAMAIS mentionner les clés API ou tokens dans les messages

### Audits
- Les audits sont stockés dans `AUDITS/` — observation uniquement, pas de modification système
- Les fichiers d'audit utilisent les tags `[OBSERVÉ]`/`[DÉDUIT]`/`[SUPPOSÉ]`/`[INCONNU]`
- Ne JAMAIS modifier l'environnement pendant un audit — observer et documenter uniquement

### Comportement général
- Toujours répondre en français
- Jamais d'action destructive sans confirmation (rm, delete, overwrite)
- Toujours logger les actions importantes dans state/
- En cas d'erreur → alerter Daniel immédiatement, ne pas masquer

## Actions qui déclenchent une relecture de ce fichier
- Avant toute publication sur un réseau social
- Avant toute modification de fichier de code
- Avant toute suppression de fichier
- Avant tout envoi d'email
- Avant toute action impliquant une API externe
