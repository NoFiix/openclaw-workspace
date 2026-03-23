# dashboard/SYSTEM.md — Architecture et fonctionnement

> Dernière mise à jour : Mars 2026

---

## OBJECTIF

Supervision en temps réel de tous les systèmes du workspace.
Outil de **lecture uniquement** — ne modifie jamais les fichiers d'état.

---

## STACK TECHNIQUE

| Composant | Technologie |
|-----------|-------------|
| Backend | Express.js (`dashboard/api/`) |
| Frontend | React + Vite (`dashboard/web/`) |
| Build | `npm run build` → `dashboard/web/dist/` |
| Supervision | PM2 `dashboard-api` |
| Port | 3001 (nginx reverse proxy) |

---

## STRUCTURE

```
dashboard/
├── api/
│   ├── server.js          ← Express + Cache-Control: no-store sur /api/*
│   ├── ecosystem.config.cjs ← PM2 config
│   └── routes/
│       ├── health.js      ← santé agents + pollers
│       ├── trading.js     ← TRADING_FACTORY données
│       ├── polymarket.js  ← POLY_FACTORY données
│       ├── content.js     ← CONTENT_FACTORY données
│       ├── costs.js       ← coûts LLM cross-factory
│       ├── storage.js     ← disk usage
│       └── docs.js        ← context bundles
└── web/
    └── src/
        └── pages/
            ├── Overview.jsx
            ├── Trading.jsx
            ├── Polymarket.jsx
            ├── Content.jsx
            ├── Costs.jsx
            ├── Infrastructure.jsx
            ├── SystemMap.jsx
            └── Docs.jsx
```

---

## RÈGLE ABSOLUE — LECTURE SEULE

Le dashboard **lit et affiche uniquement**.

Ne jamais :
- Modifier un fichier d'état depuis une route API
- Calculer une métrique métier côté frontend
- Créer une logique métier dans les routes API

Toute logique métier vit dans les systèmes sources.
Le dashboard agrège et reformule pour affichage.

---

## SOURCES DE DONNÉES PAR PAGE

### Overview
- Agrège les endpoints des autres pages
- Kill switch : `state/trading/exec/killswitch.json`
- Performance globale : `state/trading/learning/global_performance.json`

### Trading
- Wallets : `state/trading/strategies/*/wallet.json`
- Positions : `state/trading/exec/positions_testnet.json`
- Trades : `state/trading/bus/trading_exec_trade_ledger.jsonl`
- Performance : `state/trading/learning/strategy_performance.json`
- Ranking : `state/trading/learning/strategy_ranking.json`
- Candidates : `state/trading/configs/candidates_pending.json`
- Schedules : `state/trading/schedules/*.schedule.json`
- Agents état : `state/trading/memory/*.state.json`

### Polymarket
- Comptes : `POLY_FACTORY/state/accounts/ACC_POLY_*.json`
- Positions : `POLY_FACTORY/state/risk/portfolio_state.json`
- Risque global : `POLY_FACTORY/state/risk/global_risk_state.json`
- Kill switch : `POLY_FACTORY/state/risk/kill_switch_status.json`
- Trades : `POLY_FACTORY/state/trading/paper_trades_log.jsonl`

### Content
- Publications : `state/content_publish_history.json`
- Drafts : `state/drafts.json`
- Logs : `state/content_poller.log`, `state/hourly_scraper.log`

### Costs (LLM cross-factory)
- Trading : `state/trading/learning/token_costs.jsonl`
- POLY : `POLY_FACTORY/state/llm/token_costs.jsonl`
- ⚠️ Content V1 : non trackée (~30% des coûts invisibles)

### Infrastructure
- Santé pollers : `ps aux` + patterns PID
- Disk usage : `du` sur workspace
- Agents trading : `state/trading/memory/*.state.json`

### System Map
- Agents actifs : lecture schedules `state/trading/schedules/`
- Statuts runtime : `state/trading/memory/*.state.json`
- ⚠️ Certaines données encore partiellement hardcodées

---

## LOGIQUE P&L POLYMARKET — CRITIQUE

```javascript
// Capital disponible — CORRECT
const committed = openPositions.reduce((sum, p) => sum + p.value_usd, 0);
const available = acc.capital.initial - committed; // PAS current - committed

// P&L réalisé — CORRECT
const realizedPnl = closedTrades
  .filter(t => t.status === 'resolved')
  .reduce((sum, t) => sum + t.pnl_eur, 0);

// JAMAIS utiliser :
// acc.capital.current comme base → double déduction
// acc.pnl.total comme P&L réalisé → coût d'achat positions ouvertes
```

---

## DÉMARRAGE ET REBUILD

```bash
# Rebuild après toute modification React ou API
cd ~/openclaw/workspace/dashboard/web
npm run build

# Restart PM2
pm2 list
pm2 delete dashboard-api && pm2 start ecosystem.config.cjs && pm2 save

# Vérifier
pm2 logs dashboard-api --lines 20
curl -s http://localhost:3001/api/health | python3 -m json.tool | head -10
```

**⚠️ Sans rebuild, les modifications React ne sont pas visibles.**
Chaque rebuild produit un nouveau hash de bundle — force l'invalidation
du cache navigateur.

---

## CACHE

Toutes les routes `/api/*` retournent :
```
Cache-Control: no-store
Pragma: no-cache
Expires: 0
```

Implémenté dans `server.js` — ne jamais retirer ces headers.
Les données trading changent constamment, pas de cache possible.

---

## STATUT STALE

Un agent apparaît `STALE` dans le dashboard quand son dernier heartbeat
dépasse `interval * 3` secondes. Ce n'est pas forcément un problème —
c'est souvent le timing normal entre deux cycles du poller.

Exemple : BINANCE_PRICE_FEED (interval 10s) → STALE si > 30s sans update.
C'est normal entre deux cycles. Surveiller uniquement si STALE persiste > 5 min.

---

## PIÈGES CONNUS

- **Oublier le rebuild** : toute modif React invisible sans `npm run build`
- **PM2 restart** : jamais `pm2 restart dashboard-api` — toujours `delete + start`
- **Cache navigateur** : si données périmées → rebuild force un nouveau hash
- **Logique métier dans le dashboard** : toujours résister à la tentation — ça crée des incohérences inter-pages (expérimenté plusieurs fois)
- **System Map hardcodée** : certains agents sont listés statiquement — peut être en retard sur la réalité
- **Coûts LLM Content** : non trackés dans `token_costs.jsonl` — les totaux LLM sont incomplets
