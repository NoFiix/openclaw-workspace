# Dashboard OpenClaw — Accès sécurisé via tunnel SSH

## Architecture

Le dashboard tourne sur le VPS en **localhost uniquement** (port 3001).
Il n'est pas exposé directement sur Internet.
L'accès se fait via un tunnel SSH qui chiffre tout le trafic.

```
[Ta machine] :3001 ──SSH tunnel──▶ [VPS 187.77.161.191] 127.0.0.1:3001 (dashboard-api)
```

## Prérequis

- Accès SSH au VPS : `ssh openclawadmin@187.77.161.191`
- Clé SSH configurée (recommandé) ou mot de passe

## Utilisation

### 1. Ouvrir le tunnel

Depuis ta machine locale :

```bash
bash ~/dashboard-tunnel.sh
```

Ou manuellement :

```bash
ssh -N -L 3001:127.0.0.1:3001 openclawadmin@187.77.161.191
```

Le terminal reste ouvert tant que le tunnel est actif. `Ctrl+C` pour fermer.

### 2. Accéder au dashboard

Ouvrir dans le navigateur :

```
http://localhost:3001
```

### 3. Tester l'API

```bash
curl -H "x-api-key: <DASHBOARD_API_KEY>" http://localhost:3001/api/health
```

La clé API se trouve dans `dashboard/api/.env` sur le VPS.

## Dépannage

| Problème | Solution |
|----------|----------|
| `bind: Address already in use` | Un tunnel tourne déjà, ou le port 3001 est utilisé localement. `lsof -i :3001` pour identifier le process |
| `Connection refused` | Vérifier que `dashboard-api` tourne : `pm2 status` sur le VPS |
| Tunnel se coupe | Ajouter `-o ServerAliveInterval=60` à la commande SSH |

## Sécurité

- Le port 3001 du VPS est bindé sur `127.0.0.1` — inaccessible depuis Internet
- Le tunnel SSH chiffre tout le trafic (plus fort que TLS)
- Authentification par clé SSH existante
- Aucun port supplémentaire à ouvrir dans le firewall
