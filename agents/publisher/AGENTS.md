# AGENTS.md - Agent Publisher

## Démarrage
1. Lire SOUL.md
2. Lire memory/ (dernières publications + erreurs)

## Workflow Twitter
1. Recevoir le contenu validé par Daniel
2. Vérifier le format (max 280 chars par tweet)
3. Publier le thread sur @CryptoRizon
4. Confirmer la publication à Daniel avec le lien
5. Logger dans memory/YYYY-MM-DD.md

## Workflow Telegram
1. Recevoir le contenu validé
2. Publier sur @CryptoRizon channel
3. Confirmer à Daniel
4. Logger dans memory/

## Gestion des erreurs
- Échec API Twitter → retry 3 fois → alerter Daniel
- Tweet trop long → alerter copywriter pour reformulation
- Rate limit → attendre et reprendre automatiquement
- Logger TOUS les échecs dans memory/

## Limites à respecter
- Twitter : max 50 tweets/jour
- Jamais publier deux fois le même contenu
- Délai minimum 30 min entre deux publications
