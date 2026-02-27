# IDENTITY.md - Environnement technique OpenClaw

## Infrastructure
- VPS Hostinger, Ubuntu 22.04 LTS
- Docker + Node.js v22
- Conteneur gateway : openclaw-openclaw-gateway-1
- Conteneur builder : openclaw-builder-1
- Port gateway : 18789

## Chemins (dans le conteneur)
- Config : /home/node/.openclaw/openclaw.json
- Workspace : /home/node/.openclaw/workspace
- Recipes : /home/node/.openclaw/workspace/recipes/
- Skills custom : /home/node/.openclaw/workspace/skills_custom/
- State : /home/node/.openclaw/workspace/state/

## Chemins (sur le VPS)
- Config : /home/openclawadmin/openclaw/config
- Workspace : /home/openclawadmin/openclaw/workspace
- Projet : /home/openclawadmin/openclaw/

## Variables d'environnement disponibles
- OPENAI_API_KEY
- ANTHROPIC_API_KEY
- TELEGRAM_BOT_TOKEN (bot principal @OppenCllawBot)
- TELEGRAM_CHAT_ID
- BUILDER_TELEGRAM_BOT_TOKEN (bot validation/approbation)
- BUILDER_TELEGRAM_CHAT_ID
- OPENCLAW_GATEWAY_TOKEN

## Zones autorisées
- ✅ workspace/recipes/
- ✅ workspace/skills_custom/
- ✅ workspace/state/
- ❌ /src, /dist, package.json, docker-compose.yml

## Sécurité
- Jamais stocker de secrets dans workspace/
- Toute modification de code → diff → validation Telegram avant application
- Toute publication externe → validation Telegram

## Modèle Haiku ajouté
- anthropic/claude-haiku-4-5 → tâches ultra légères (notifications, tri, résumés rapides, support)
