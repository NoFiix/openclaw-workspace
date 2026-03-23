# runbooks/dashboard.md — Opérations Dashboard

---

## VÉRIFIER L'ÉTAT DU DASHBOARD

```bash
# PM2 status
pm2 show dashboard-api | grep -E "status|cpu|memory|uptime"

# Réponse API health
curl -s http://localhost:3001/api/health \
  | python3 -m json.tool | head -20

# Logs récents
pm2 logs dashboard-api --lines 20
```

---

## REDÉMARRER LE DASHBOARD

```bash
# TOUJOURS cette séquence — jamais pm2 restart
pm2 delete dashboard-api
pm2 start ~/openclaw/workspace/dashboard/api/ecosystem.config.cjs
pm2 save

# Vérifier
sleep 3
pm2 show dashboard-api | grep status
curl -s http://localhost:3001/api/health | python3 -m json.tool | head -5
```

---

## MODIFIER LE FRONTEND (React)

```bash
# 1. Modifier les fichiers dans dashboard/web/src/

# 2. Rebuild obligatoire
cd ~/openclaw/workspace/dashboard/web
npm run build

# 3. Restart dashboard
pm2 delete dashboard-api
pm2 start ~/openclaw/workspace/dashboard/api/ecosystem.config.cjs
pm2 save

# 4. Vérifier le nouveau hash de bundle
ls ~/openclaw/workspace/dashboard/web/dist/assets/
```

---

## MODIFIER L'API (Express)

```bash
# 1. Modifier les fichiers dans dashboard/api/routes/

# 2. Restart dashboard (pas besoin de rebuild pour l'API seule)
pm2 delete dashboard-api
pm2 start ~/openclaw/workspace/dashboard/api/ecosystem.config.cjs
pm2 save

# 3. Tester l'endpoint modifié
curl -s http://localhost:3001/api/<endpoint> | python3 -m json.tool
```

---

## AJOUTER UNE NOUVELLE SECTION

Règle additive — ne jamais modifier ce qui existe :

1. Créer un nouvel agrégat dans `dashboard/api/routes/<système>.js`
2. Créer un nouvel endpoint dans `dashboard/api/server.js`
3. Créer une nouvelle page dans `dashboard/web/src/pages/<Système>.jsx`
4. Ajouter le lien dans le menu de navigation
5. Rebuild + restart

---

## DIAGNOSTIQUER DONNÉES PÉRIMÉES

```bash
# 1. Vider le cache navigateur (Ctrl+Shift+R)
# Si ça ne suffit pas :

# 2. Vérifier les headers Cache-Control
curl -I http://localhost:3001/api/health | grep -i cache

# 3. Rebuild pour forcer nouveau hash bundle
cd ~/openclaw/workspace/dashboard/web && npm run build

# 4. Vérifier que les fichiers source existent
ls ~/openclaw/workspace/state/trading/strategies/*/wallet.json
cat ~/openclaw/workspace/POLY_FACTORY/state/accounts/ACC_POLY_OPP_SCORER.json \
  | python3 -m json.tool | head -10
```
