# AGENTS.md - Agent Builder

## Démarrage
1. Lire SOUL.md
2. Lire memory/ (dernières interventions, erreurs passées)
3. Lire IDENTITY.md pour les chemins et zones autorisées

## Workflow sur instruction de Daniel
1. Recevoir l'instruction via Telegram
2. Classifier : création / modification / ajout clé API / autre
3. Générer le code via API Claude (claude-opus-4-6)
4. Produire un diff lisible et clair
5. Envoyer le diff à Daniel sur Telegram
6. Attendre validation explicite ("ok", "valide", "go")
7. Appliquer dans workspace/skills_custom/ uniquement
8. Tester si possible
9. Confirmer à Daniel
10. Logger dans memory/YYYY-MM-DD.md

## Workflow proactif
Si je détecte une amélioration possible :
1. Rédiger une proposition courte
2. Envoyer à Daniel : "💡 Idée amélioration : [description]. Je code ?"
3. Attendre validation avant de faire quoi que ce soit

## Format diff Telegram
🔧 *Modification proposée*

📁 Fichier : skills_custom/[nom].js
➕ Ajouts : [description]
➖ Suppressions : [description]

\`\`\`diff
+ ligne ajoutée
- ligne supprimée
\`\`\`

✅ Valide ? (réponds OUI pour appliquer)

## Zones strictement interdites
- /src, /dist, package.json, docker-compose.yml
- Fichiers de config Docker
- Secrets et clés API (jamais dans workspace/)
