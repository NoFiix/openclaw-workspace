# TRADING_FACTORY/STATE.md — Sources de vérité

> ⏸️ SUSPENDU le 2026-04-28 — économie ressources API.
> Pour relancer : `docker exec -d openclaw-openclaw-gateway-1 sh -c "node /home/node/.openclaw/workspace/TRADING_FACTORY/poller.js >> /home/node/.openclaw/workspace/state/trading/poller.log 2>&1"`
> Puis décommenter les crons (@reboot, watchdog) et la ligne dans docker-start-pollers.sh.

> `state/trading/` ne bouge jamais. Toute donnée dashboard doit être tracée ici.

---

## FICHIERS CRITIQUES

| Fichier | Écrit par | Vérité | Notes |
|---------|-----------|--------|-------|
| `strategies/*/wallet.json` | Executors via walletOnClose | ✅ Capital, cash, PnL | `cash` = walletOnClose() uniquement |
| `exec/positions_testnet.json` | TESTNET_EXECUTOR | ✅ Positions testnet | |
| `exec/positions.json` | PAPER_EXECUTOR | ✅ Positions paper | ⚠️ double source |
| `strategies/*/positions.json` | Executors | ✅ Positions par stratégie | ⚠️ double source |
| `exec/killswitch.json` | KILL_SWITCH_GUARDIAN | ✅ Kill switch | Reset manuel uniquement |
| `configs/strategies_registry.json` | STRATEGY_SCOUT | ✅ Stratégies actives | |
| `configs/candidates_pending.json` | STRATEGY_SCOUT | ✅ Candidats | Modifier manuellement |
| `learning/token_costs.jsonl` | logTokens.js | ✅ Coûts LLM bruts | |
| `learning/strategy_ranking.json` | PERFORMANCE_ANALYST | Dérivé | |
| `memory/*.state.json` | agentRuntime.js | Runtime + curseur bus | STALE si >interval×3s |
| `schedules/*.schedule.json` | Manuel | ✅ Config schedules | `agent_id` = nom exact dossier TRADING_FACTORY/ |
| `audit/*.jsonl` | Système | Append-only | Jamais purger |

**Tous les `learning/*.json` sauf `token_costs.jsonl` sont dérivés** — remonter aux wallets/positions si incohérence.

---

## STRUCTURES MINIMALES

**wallet.json** : `cash` | `equity` | `allocated` | `status` | `trade_count`

**strategies_registry.json** : `enabled` | `lifecycle_status` | `live_approved` | `min_cash_threshold`
Lifecycle : `paper_active` | `paper_ready` | `paper_testing` | `stopped`

---

## BUS EVENTS

| Topic (`trading.`) | Producteur → Consommateur | TTL |
|--------------------|--------------------------|-----|
| `raw.market.ticker` | BINANCE_PRICE_FEED → MARKET_EYE | 1j |
| `intel.market.features` | MARKET_EYE → REGIME_DETECTOR, TRADE_GENERATOR | 2j |
| `intel.whale.signal` | WHALE_ANALYZER → REGIME_DETECTOR | 7j |
| `intel.regime` | REGIME_DETECTOR → TRADE_GENERATOR | 90j |
| `intel.prediction` | PREDICTOR → ⚠️ inconnu | 7j |
| `strategy.trade.proposal` | TRADE_GENERATOR → RISK_MANAGER | 90j |
| `strategy.order.plan` | RISK_MANAGER → POLICY_ENGINE | — |
| `exec.order.submit` | TRADING_ORCHESTRATOR → Executors | — |
| `exec.trade.ledger` | Executors → PERFORMANCE_ANALYST | 365j |
| `ops.killswitch.state` | KILL_SWITCH_GUARDIAN → POLICY_ENGINE | — |

Topics = string constants dans le code. Déplacer TRADING_FACTORY/ n'affecte pas les topics.
Rotation : `bus_rotation.js` (cron `0 3 * * *`) + `bus_cleanup_trading.js` (`30 3 * * *`)

---

## HIÉRARCHIE DES SOURCES

1. `strategies/*/wallet.json` → capital, cash, PnL réalisé
2. `exec/positions_testnet.json` → positions ouvertes
3. `exec/killswitch.json` → kill switch
4. `learning/strategy_ranking.json` → ranking (dérivé)
5. `bus/*.jsonl` → historique events
6. `poller.log` → debug uniquement
