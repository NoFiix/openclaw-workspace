# MEMORY.md - Mémoire long terme d'OpenClaw

## Dernière mise à jour
2026-02-26

## Modèles IA disponibles
### OpenAI (OPENAI_API_KEY)
- openai/gpt-4o-mini → tâches légères, résumés, classification
- openai/gpt-4o → tâches intermédiaires

### Anthropic (ANTHROPIC_API_KEY)
- anthropic/claude-haiku-4-5 → notifications, tri emails, résumés rapides, support client
- anthropic/claude-sonnet-4-5 → rédaction, analyse, storytelling
- anthropic/claude-opus-4-6 → code, tâches critiques, auto-amélioration

## Règle de routing
Score = Importance (1-5) + Sensibilité (1-5) + Complexité (1-5)
- 3-4 → claude-haiku-4-5
- 5-6 → gpt-4o-mini
- 7-8 → gpt-4o
- 9-11 → claude-sonnet-4-5
- 12-15 → claude-opus-4-6

## Recipes actives
- daily_crypto_recap : tous les jours à 19h Europe/Paris
  Pipeline : digest numéroté → Daniel choisit → post Twitter réécrit → validation → publication

## Ce que Daniel attend de moi
- Réponses courtes, directes, sans remplissage
- Toujours proposer des améliorations proactivement
- Jamais agir sur l'externe sans validation Telegram
- Jamais modifier le core OpenClaw
- Logger toutes les actions importantes dans workspace/state/

## Leçons apprises
_(à remplir au fil du temps)_

## Projets en cours
- Configuration OpenClaw complète (infrastructure IA personnelle)
- Pipeline Twitter CryptoRizon automatisé
- Tri emails tutorizonofficiel@gmail.com + khuddan@gmail.com
