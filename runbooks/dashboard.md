# runbooks/dashboard.md

## ÉTAT

```bash
pm2 show dashboard-api | grep -E "status|uptime"
curl -s http://localhost:3001/api/health | python3 -m json.tool | head -10
```

## REBUILD + RESTART

```bash
cd ~/openclaw/workspace/dashboard/web && npm run build
pm2 delete dashboard-api && pm2 start ~/openclaw/workspace/dashboard/api/ecosystem.config.cjs && pm2 save
```

## AJOUTER UNE SECTION (règle additive)

1. Agrégat dans `dashboard/api/routes/<système>.js`
2. Endpoint dans `dashboard/api/server.js`
3. Page dans `dashboard/web/src/pages/<Système>.jsx`
4. Rebuild + restart

## DONNÉES PÉRIMÉES

```bash
# Vider cache navigateur (Ctrl+Shift+R) ou :
cd ~/openclaw/workspace/dashboard/web && npm run build
```
