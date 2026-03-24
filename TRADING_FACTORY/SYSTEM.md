# TRADING_FACTORY/SYSTEM.md

> Paper trading — Binance Testnet. 30 jours minimum avant live.

---

## STACK

| Composant | Valeur |
|-----------|--------|
| Runtime | Node.js v22 + Docker |
| Poller | `TRADING_FACTORY/poller.js` (docker-start-pollers.sh) |
| Bus | `state/trading/bus/*.jsonl` |
| État | `state/trading/` (JAMAIS DÉPLACER) |
| Symbols | BTCUSDT, ETHUSDT, BNBUSDT |
| Timeframes | 5m, 1h, 4h |

---

## PIPELINE — ORDRE OBLIGATOIRE, AUCUN SHORTCUT

```
BINANCE_PRICE_FEED → raw.market.ticker
MARKET_EYE        → intel.market.features (RSI/BB/MACD/ATR sur 5m,1h,4h)
WHALE_ANALYZER    → intel.whale.signal
REGIME_DETECTOR   → intel.regime v2 (régime + whale_context)
TRADE_GENERATOR   → hasSignal() → Haiku si signal → strategy.trade.proposal
RISK_MANAGER      → 1% risk, max 5 positions → strategy.order.plan
POLICY_ENGINE     → stratégie, env, horaire, notional → strategy.policy.decision
TRADING_ORCHESTRATOR → corrèle plan + decision → exec.order.submit
TESTNET_EXECUTOR  → MARKET + OCO (TP+SL) → walletOnOpen() / walletOnClose()
```

---

## AGENTS ET SCHEDULES

| Agent | Interval | LLM |
|-------|----------|-----|
| BINANCE_PRICE_FEED | 30s | — |
| TESTNET_EXECUTOR | 30s | — |
| POLICY_ENGINE | 30s | — |
| KILL_SWITCH_GUARDIAN | 60s | — |
| RISK_MANAGER | 60s | — |
| TRADING_PUBLISHER | 60s | Haiku |
| NEWS_FEED | 300s | — |
| NEWS_SCORING | 300s | Haiku |
| MARKET_EYE | 300s | — |
| PREDICTOR | 300s | — ⚠️ consommateur inconnu |
| WHALE_FEED | 300s +15s | — |
| WHALE_ANALYZER | 300s +60s | — |
| REGIME_DETECTOR | 300s | — |
| TRADE_GENERATOR | 300s | Haiku |
| TRADING_ORCHESTRATOR | 10s | — |
| PERFORMANCE_ANALYST | 3600s | — |
| STRATEGY_GATEKEEPER | 3600s | — |
| GLOBAL_TOKEN_TRACKER | 3600s | — |
| GLOBAL_TOKEN_ANALYST | 3600s | Sonnet (lun+jeu) |
| TRADE_STRATEGY_TUNER | 604800s | Sonnet (si 30+ trades) |
| STRATEGY_SCOUT | 172800s | Sonnet |

⚠️ STRATEGY_RESEARCHER désactivé (`enabled: false`) — remplacé par STRATEGY_SCOUT.

---

## 4 STRATÉGIES ACTIVES

| Stratégie | Signal | Timeframe |
|-----------|--------|-----------|
| MeanReversion | BB_pctB < 0.25/>0.75 + RSI < 40/>60 | 5m + 1h |
| Momentum | MACD 1h+4h même signe (ou 1h seul si conf≥0.7) + TREND | 1h + 4h |
| Breakout | bbWidth_1h < 0.03 | 1h |
| NewsTrading | urgency ≥ 8 + age < 1h | temps réel |

⚠️ Seuils calibrés pour 5m — ne jamais revenir aux anciens (BB<0.15, RSI<35, bbWidth<0.02).

---

## WALLETS

```
state/trading/strategies/{MeanReversion|Momentum|Breakout|NewsTrading}/wallet.json
```

- `walletOnOpen()` → UNIQUEMENT si position confirmée + cash suffisant
- `walletOnClose()` → UNIQUEMENT à la clôture réelle (TP ou SL)
- `cash < min_cash_threshold` → `status: "suspended"`

---

## KILL SWITCH

**Déclenchement :** perte >3%/24h | 3+ erreurs executor | exchange DOWN >5min | data DEGRADED >15min
**Comportement :** 0 nouvel ordre | positions NON annulées | alerte Telegram | reset MANUEL uniquement
**Fichier :** `state/trading/exec/killswitch.json`

---

## AGENTS SPÉCIFIQUES

| Agent | Points clés |
|-------|------------|
| WHALE_ANALYZER | score ∈ [-1,+1] fenêtre 6h, consultatif uniquement |
| REGIME_DETECTOR | TREND_UP/DOWN/RANGE/PANIC/EUPHORIA/VOLATILE/UNKNOWN + whale_context |
| STRATEGY_GATEKEEPER | score Expectancy 35%+PF 30%+Drawdown 20%+Sharpe 10%+Count 5% — seuils 0.60/0.40 |
| TRADE_STRATEGY_TUNER | MIN_TRADES=30, 1 param/itération, amplitudes RSI±3/BB±0.03/MACD±0.0003 |
| STRATEGY_SCOUT | 1/48h, validation manuelle `candidates_pending.json` — statuts : `pending_review` / `approved_config_ready` / `approved_dev_required` / `rejected` |

---

## POINTS D'ATTENTION

| Point | Statut |
|-------|--------|
| PREDICTOR orphelin (0 consommateur confirmé) | À vérifier |
| Double bus_cleanup (02:00 + 03:30) | Idempotent, à nettoyer |
| `news:high_impact` sans producteur | Backlog — NEWS_STRAT inopérante |
