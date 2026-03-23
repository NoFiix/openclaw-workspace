# TRADING_FACTORY/SYSTEM.md — Architecture et fonctionnement

> Dernière mise à jour : Mars 2026
> Voir aussi : `TRADING_FACTORY/STATE.md` pour les sources de vérité
> Source : CONTEXT_BUNDLE_TRADING.md + corrections post-migration Mars 2026

---

## OBJECTIF

Générer des profits sur Binance via trading algorithmique multi-stratégies.
Pipeline entièrement automatisé : détection de signal → sizing → risk → exécution.
Supervision humaine sur les décisions critiques via Telegram.

**Statut actuel :** Paper trading testnet — 30 jours minimum avant passage live.

---

## STACK TECHNIQUE

| Composant | Technologie |
|-----------|-------------|
| Runtime | Node.js v22 |
| Exécution | Docker container `openclaw-openclaw-gateway-1` |
| Poller | `TRADING_FACTORY/poller.js` (daemon, lancé par docker-start-pollers.sh) |
| Bus events | Fichiers JSONL dans `state/trading/bus/` |
| Schedules | JSON dans `state/trading/schedules/` |
| État | `state/trading/` (NE JAMAIS DÉPLACER) |
| Exchange | Binance Testnet (paper) → Binance Mainnet (live) |
| Symbols | BTCUSDT, ETHUSDT, BNBUSDT |
| Timeframes | 5m, 1h, 4h |

---

## ARCHITECTURE — 25 AGENTS EN 4 COUCHES

```
COUCHE 0 — DATA & OPS
  BINANCE_PRICE_FEED (30s)  → trading.raw.market.ticker
  MARKET_EYE (300s)         → trading.intel.market.features
  NEWS_FEED (300s)          → trading.raw.news.article + raw.social.post
  WHALE_FEED (300s +15s)    → trading.raw.whale.transfer
  KILL_SWITCH_GUARDIAN (60s)→ trading.ops.killswitch.state
  SYSTEM_WATCHDOG           → surveillance santé agents
  GLOBAL_TOKEN_TRACKER (3600s) → learning/token_summary.json
  GLOBAL_TOKEN_ANALYST (lun+jeu 8h UTC) → learning/token_recommendations.json
        ↓
COUCHE 1 — INTELLIGENCE
  NEWS_SCORING (300s)       → trading.intel.news.event
  PREDICTOR (300s)          → trading.intel.prediction (⚠️ consommateur inconnu)
  WHALE_ANALYZER (300s +60s)→ trading.intel.whale.signal
  REGIME_DETECTOR (300s)    → trading.intel.regime (v2 avec whale_context)
        ↓
COUCHE 2 — STRATÉGIE
  TRADE_GENERATOR (300s)    → trading.strategy.trade.proposal
  RISK_MANAGER (60s)        → trading.strategy.order.plan
  POLICY_ENGINE (30s)       → trading.strategy.policy.decision
  TRADING_ORCHESTRATOR (10s)→ trading.exec.order.submit
  STRATEGY_GATEKEEPER (3600s)→ active/désactive stratégies
  TRADE_STRATEGY_TUNER (604800s) → ajuste paramètres stratégies
        ↓
COUCHE 3 — EXÉCUTION
  TESTNET_EXECUTOR (30s)    → positions + ledger
  PAPER_EXECUTOR            → simulation paper
        ↓
COUCHE 4 — OPTIMISATION
  PERFORMANCE_ANALYST (3600s) → métriques + ranking
  STRATEGY_SCOUT (172800s)  → découverte candidates (agent unique actif)
  TRADING_PUBLISHER (60s)   → notifications Telegram
  POLY_TRADING_PUBLISHER    → notifications Telegram POLY
  GLOBAL_TOKEN_TRACKER      → suivi coûts LLM
  GLOBAL_TOKEN_ANALYST      → optimisation coûts LLM
```

---

## PIPELINE COMPLET — UN TRADE

```
BINANCE_PRICE_FEED (30s)
    ↓ trading.raw.market.ticker
MARKET_EYE (300s)
    ↓ trading.intel.market.features (RSI/BB/MACD/ATR sur 5m, 1h, 4h)
WHALE_ANALYZER (300s)
    ↓ trading.intel.whale.signal (score [-1,+1] fenêtre 6h)
REGIME_DETECTOR (300s)
    ↓ trading.intel.regime v2 (régime + whale_context)
TRADE_GENERATOR (300s)
    → hasSignal() — filtre pré-LLM (skip si pas de signal)
    → si signal → appel Haiku → proposal BUY/SELL/HOLD
    → whale_context ajuste confidence ±0.07 max
    ↓ trading.strategy.trade.proposal
RISK_MANAGER (60s)
    → vérif limites : 1% risk, max 5 positions, pas doublon symbol
    ↓ trading.strategy.order.plan
POLICY_ENGINE (30s)
    → vérif stratégie, asset, env, horaire, notional, blacklist
    → si > seuil USD → demande approbation Telegram
    ↓ trading.strategy.policy.decision
TRADING_ORCHESTRATOR (10s)
    → corrèle order.plan + policy.decision
    → états : PENDING_POLICY → APPROVED/BLOCKED/PENDING_HUMAN/EXPIRED
    ↓ trading.exec.order.submit
TESTNET_EXECUTOR (30s)
    → ordre MARKET sur Binance Testnet
    → OCO automatique (TP + SL)
    → walletOnOpen() → met à jour wallet
    ↓ trading.exec.position.snapshot + trading.exec.trade.ledger
(à la clôture TP/SL)
    → walletOnClose() → met à jour cash, equity, PnL, ROI
```

**Règle absolue :** Aucun shortcut dans ce pipeline. Chaque étape est obligatoire.

---

## SCHEDULES COMPLETS

| Agent | every_seconds | LLM | Notes |
|-------|--------------|-----|-------|
| BINANCE_PRICE_FEED | 30 | Non | |
| TESTNET_EXECUTOR | 30 | Non | |
| POLICY_ENGINE | 30 | Non | |
| KILL_SWITCH_GUARDIAN | 60 | Non | |
| RISK_MANAGER | 60 | Non | |
| TRADING_PUBLISHER | 60 | Haiku | ~150 tokens/trade |
| NEWS_FEED | 300 | Non | |
| NEWS_SCORING | 300 | Haiku | ~420 tokens/news |
| MARKET_EYE | 300 | Non | |
| PREDICTOR | 300 | Non | ⚠️ consommateur inconnu |
| WHALE_FEED | 300 | Non | jitter +15s |
| WHALE_ANALYZER | 300 | Non | jitter +60s (après WHALE_FEED) |
| REGIME_DETECTOR | 300 | Non | |
| TRADE_GENERATOR | 300 | Haiku | ~1600 tokens/appel |
| TRADING_ORCHESTRATOR | 10 | Non | |
| PERFORMANCE_ANALYST | 3600 | Non | |
| STRATEGY_GATEKEEPER | 3600 | Non | |
| GLOBAL_TOKEN_TRACKER | 3600 | Non | bilan Telegram 20h UTC |
| GLOBAL_TOKEN_ANALYST | 3600 | Sonnet | vérifie lun+jeu 8h UTC |
| TRADE_STRATEGY_TUNER | 604800 | Sonnet | 1x/semaine, attend 30 trades |
| STRATEGY_SCOUT | 172800 | Sonnet | agent unique de découverte |

**⚠️ STRATEGY_RESEARCHER désactivé** (`enabled: false`) — remplacé par STRATEGY_SCOUT.

---

## 4 STRATÉGIES ACTIVES

| Stratégie | Logique | Timeframe | Statut |
|-----------|---------|-----------|--------|
| MeanReversion | RSI oversold/overbought + BB_pctB | 5m + 1h | Paper active |
| Momentum | MACD 1h aligné + régime TREND | 1h + 4h | Paper active |
| Breakout | BB squeeze (bbWidth < 0.03) | 1h | Paper active |
| NewsTrading | News urgency >= 8 (< 1h) | Temps réel | Paper active |

### Seuils hasSignal() — calibrés pour timeframe 5m

⚠️ Ces seuils ont été mis à jour après BUG-005 (passage 1m → 5m le 9 mars).
Ne pas utiliser les anciens seuils (RSI<35, BB<0.15, bbWidth<0.02).

```javascript
MeanReversion : BB_pctB_5m < 0.25 || > 0.75
                RSI_5m < 40 || > 60
                RSI_1h < 40 || > 60 (confirmation)

Momentum :      MACD_1h ET MACD_4h même signe
                OU MACD_1h seul si conf >= 0.7
                + régime TREND_UP ou TREND_DOWN

Breakout :      bbWidth_1h < 0.03 (squeeze)

NewsTrading :   recentNews.some(n => n.urgency >= 8 && age < 1h)
```

---

## MULTI-WALLET PAR STRATÉGIE

Chaque stratégie a son propre wallet virtuel isolé de $1000 :

```
state/trading/strategies/
├── MeanReversion/wallet.json
├── Momentum/wallet.json
├── Breakout/wallet.json
└── NewsTrading/wallet.json
```

**Règles critiques :**
- `walletOnOpen()` → appelé UNIQUEMENT quand position confirmée ouverte
- `walletOnClose()` → appelé UNIQUEMENT à la clôture réelle (TP ou SL)
- Circuit breaker : `cash < min_cash_threshold` → `status: "suspended"`
- Ne jamais modifier `wallet.json` directement sauf reset explicite validé

---

## AGENTS DÉTAILLÉS — POINTS CLÉS

### WHALE_FEED
- Sources : Etherscan REST (ETH natif + USDT/USDC/WBTC ERC20)
- Seuils : ETH/WBTC >= $500k | USDT/USDC >= $1M
- Déduplication par tx_hash, TTL 2h
- Zéro LLM
- Config : `state/trading/configs/WHALE_FEED.config.json`
- Adresses surveillées : `state/trading/configs/exchange_addresses.json`

### WHALE_ANALYZER
- Classification : TO_EXCHANGE / FROM_EXCHANGE / STABLE_TO_EXCHANGE / STABLE_MINT / MM_FLOW
- Score whale_flow_score ∈ [-1, +1] sur fenêtre 6h glissante
- Bias : BULLISH (>0.30) / BEARISH (<-0.30) / NEUTRAL
- Signal consultatif uniquement — jamais déclencheur seul
- Zéro LLM

### REGIME_DETECTOR v2
- Régimes : TREND_UP / TREND_DOWN / RANGE / PANIC / EUPHORIA / VOLATILE / UNKNOWN
- whale_context : bias (ACCUMULATION/DISTRIBUTION/NEUTRAL/MIXED) + strength + confidence
- Payload version : `intel.regime.v2`

### TRADE_GENERATOR
- whale_context lu depuis régime v2 → ajustement confidence ±0.07 max
- Haiku uniquement si hasSignal() passe (évite appels inutiles)

### STRATEGY_GATEKEEPER
- Score pondéré : Expectancy 35% + PF 30% + Drawdown 20% + Sharpe 10% + Count 5%
- Seuils : ≥ 0.60 = active | 0.40-0.59 = testing | < 0.40 = alerte Telegram

### TRADE_STRATEGY_TUNER
- MIN_TRADES_FIRST_RUN = 30 (pas de tuning avant 30 trades)
- 1 seul paramètre modifié par itération
- Amplitudes bornées : RSI ±3 | BB ±0.03 | MACD ±0.0003
- Rollback auto si sous-performance sur 10+ nouveaux trades
- Anti-oscillation : blacklist (param, valeur) sur 3 dernières versions
- Stop si score > 0.70 (SCORE_TUNING_CEILING)

### PERFORMANCE_ANALYST — Ranking stratégies
- Statuts : `insufficient_data` (0 trade) → `warming_up` (1-9) → `ranked` (≥ 10)
- Critères : ROI net 30% + Drawdown inversé 20% + Profit factor 20% +
  Win rate 10% + Nb trades 10% + Stabilité 14j 10%
- Fichier : `state/trading/learning/strategy_ranking.json`

---

## KILL SWITCH

**Conditions de déclenchement automatique :**
- Perte > 3% capital total en 24h glissantes
- 3+ erreurs TESTNET_EXECUTOR consécutives
- Exchange health DOWN > 5 minutes
- Data quality DEGRADED > 15 minutes

**Quand déclenché :**
- Aucun nouvel ordre soumis
- Positions ouvertes NON annulées automatiquement
- Alerte Telegram immédiate
- Reset UNIQUEMENT manuel

**Fichier état :** `state/trading/exec/killswitch.json`

---

## STRATÉGIES CANDIDATES (STRATEGY_SCOUT)

```
STRATEGY_SCOUT (toutes les 48h, max 1 candidate/run)
    ↓ message Telegram informatif (texte brut, sans boutons)
    ↓ écrit dans candidates_pending.json
    ↓ Dan modifie manuellement le statut :
        pending_review      → ne rien faire
        approved_config_ready → registry (enabled:false, paper_ready)
        approved_dev_required → ne pas toucher au registry
        rejected            → ne rien faire
    ↓ au prochain run : STRATEGY_SCOUT lit et agit
```

**Format candidates_pending.json :** objet indexé par `candidate_id`
avec `last_seq` monotone et `registry_synced` comme garde idempotence.

---

## ADRESSES WHALE SURVEILLÉES

| Catégorie | Exchanges |
|-----------|-----------|
| CEX | Binance, Coinbase, Kraken, Bitfinex, OKX, Huobi, KuCoin |
| Stablecoin issuers | Tether, Circle |
| Market makers | Wintermute, Jump (contexte seulement) |
| Bridges filtrés | Arbitrum, Optimism, Polygon |
| Protocoles filtrés | ETH2 deposit, WETH |

---

## POINTS D'ATTENTION (AUDIT 2026-03-15)

Ces points ont été observés lors de l'audit. Vérifier s'ils sont encore valides :

| Point | Observation | Statut |
|-------|-------------|--------|
| PREDICTOR orphelin | Produit des prédictions mais aucun consommateur identifié | À vérifier |
| Double bus_cleanup | `bus_cleanup_trading.js` lancé 2x/jour (02:00 + 03:30) | Idempotent mais à nettoyer |
| NEWS_SCORING → POLY bridge | `news:high_impact` non implémenté | En backlog |
| HUMAN_APPROVAL | Mécanisme d'approbation Telegram partiellement implémenté | À valider |

---

## COÛTS LLM ESTIMÉS

| Agent | Modèle | Fréquence | Coût estimé/mois |
|-------|--------|-----------|-----------------|
| TRADE_GENERATOR | Haiku | ~3 appels/cycle si signal | ~$5 |
| NEWS_SCORING | Haiku | ~420 tokens/news | ~$2 |
| TRADING_PUBLISHER | Haiku | ~150 tokens/trade | ~$0.5 |
| PERFORMANCE_ANALYST | Haiku | 1/jour | ~$0.5 |
| STRATEGY_SCOUT | Sonnet | 1/48h | ~$1 |
| TRADE_STRATEGY_TUNER | Sonnet | 1/semaine si 30+ trades | ~$0.5 |
| GLOBAL_TOKEN_ANALYST | Sonnet | 2x/semaine | ~$1 |

**Source tracking :** `state/trading/learning/token_costs.jsonl`
**Projection mensuelle :** ~$10-12/mois

---

## COMMANDES UTILES

```bash
# Vérifier que le poller tourne
docker exec openclaw-openclaw-gateway-1 sh -c "
ps aux | grep 'TRADING_FACTORY/poller' | grep -v grep
"

# Logs du poller trading
docker exec openclaw-openclaw-gateway-1 sh -c "
tail -50 /home/node/.openclaw/workspace/state/trading/poller.log
"

# Relancer le poller trading manuellement
docker exec openclaw-openclaw-gateway-1 sh -c "
pkill -f 'TRADING_FACTORY/poller.js' && echo 'Arrêté'
"
docker exec -d openclaw-openclaw-gateway-1 sh -c "
node /home/node/.openclaw/workspace/TRADING_FACTORY/poller.js \
  >> /home/node/.openclaw/workspace/state/trading/poller.log 2>&1
"

# Wallets des 4 stratégies
for s in MeanReversion Momentum Breakout NewsTrading; do
  echo "=== $s ==="
  cat ~/openclaw/workspace/state/trading/strategies/$s/wallet.json \
    | python3 -m json.tool
done

# Positions ouvertes
cat ~/openclaw/workspace/state/trading/exec/positions_testnet.json \
  | python3 -m json.tool

# Kill switch état
cat ~/openclaw/workspace/state/trading/exec/killswitch.json \
  | python3 -m json.tool

# Ranking stratégies
cat ~/openclaw/workspace/state/trading/learning/strategy_ranking.json \
  | python3 -m json.tool

# Schedules actifs
grep -l '"enabled": true' \
  ~/openclaw/workspace/state/trading/schedules/*.json \
  | xargs -I{} basename {} .schedule.json | sort
```

---

## PIÈGES CONNUS

- **Timeframe mismatch silencieux** : changer le timeframe d'un agent sans mettre à jour les consommateurs → 0 signal pendant des jours (BUG-001)
- **walletOnOpen() mal placé** : appeler avant confirmation = wallet négatif + circuit breaker (BUG-004)
- **Curseur bus à 0** : un nouvel executor retraite tout l'historique au démarrage (BUG-004)
- **Seuils hasSignal() 1m vs 5m** : ne jamais réutiliser les anciens seuils (BB<0.15, RSI<35) (BUG-005)
- **STRATEGY_RESEARCHER** : désactivé — ne pas réactiver (remplacé par STRATEGY_SCOUT, DEC-010)
- **PREDICTOR** : topic potentiellement orphelin (aucun consommateur confirmé)
