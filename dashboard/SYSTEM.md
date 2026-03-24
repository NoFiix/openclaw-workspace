# dashboard/SYSTEM.md

> Lecture seule. Zéro logique métier. Rebuild obligatoire après toute modif React.

---

## STACK

| Composant | Valeur |
|-----------|--------|
| Backend | Express.js `dashboard/api/` |
| Frontend | React + Vite `dashboard/web/` |
| PM2 | `dashboard-api` port 3001 |
| Cache | `Cache-Control: no-store` sur toutes les routes `/api/*` — ne jamais retirer |

---

## SOURCES PAR PAGE

| Page | Sources |
|------|---------|
| Trading | `state/trading/strategies/*/wallet.json` + `exec/positions_testnet.json` + `exec/killswitch.json` + `learning/strategy_ranking.json` + `configs/candidates_pending.json` + `memory/*.state.json` |
| Polymarket | `POLY_FACTORY/state/accounts/ACC_POLY_*.json` + `risk/portfolio_state.json` + `risk/global_risk_state.json` + `risk/kill_switch_status.json` |
| Content | `state/content_publish_history.json` + `state/drafts.json` + logs |
| Costs | `state/trading/learning/token_costs.jsonl` + `POLY_FACTORY/state/llm/token_costs.jsonl` ⚠️ Content non trackée |
| Infrastructure | `ps aux` + `du` + `memory/*.state.json` |

---

## LOGIQUE P&L POLY — NE PAS MODIFIER

```javascript
const available = acc.capital.initial - openPositions.reduce((s,p) => s + p.value_usd, 0);
const realizedPnl = closedTrades.filter(t => t.status === 'resolved').reduce((s,t) => s + t.pnl_eur, 0);
// JAMAIS : acc.capital.current | acc.pnl.total
```

---

## REBUILD ET RESTART

```bash
cd ~/openclaw/workspace/dashboard/web && npm run build
pm2 delete dashboard-api && pm2 start ecosystem.config.cjs && pm2 save
```

---

## POINTS D'ATTENTION

| Point | Note |
|-------|------|
| STALE agent | Normal si < 5 min. Surveiller si persiste. |
| System Map | Partiellement hardcodée — peut être en retard sur la réalité |
| Coûts LLM Content | Non trackés — totaux LLM incomplets |
