# AGENTS — TRADE_GENERATOR

## Objectif
Produire des TradeProposal de haute qualité, reproductibles et compatibles
avec RISK_MANAGER et POLICY_GATEKEEPER. Une proposal médiocre vaut moins qu'un HOLD.

## Event Interface

### Inputs (topics consommés)
| Topic | Rôle |
|-------|------|
| `trading.intel.market.features` | RSI, BB, ATR, MACD, volume z-score |
| `trading.intel.prediction` | direction_prob, confidence PREDICTOR |
| `trading.intel.regime` | RANGE/TREND/PANIC/NEWS_DRIVEN/EUPHORIA |
| `trading.intel.sentiment.score` | Fear & Greed, sentiment social |
| `trading.intel.news.event` | Events scorés par NEWS_SCORING |
| `trading.intel.onchain.flows` | Flux exchange, stablecoin flows |
| `trading.intel.whale.alert` | Mouvements baleines |
| `trading.ops.killswitch.state` | Si TRIPPED → HOLD immédiat |

### Output (topic produit)
`trading.strategy.trade.proposal`

### Payload schema
```json
{
  "strategy": "Momentum|MeanReversion|NewsTrading|WhaleFollowing|SentimentExtremes|SwingPosition",
  "side": "BUY|SELL|HOLD",
  "asset": "BTCUSDT",
  "confidence": 0.0,
  "confirmation_mode": "NewsTrading|Momentum|MeanReversion|...",
  "setup": { "entry": 0, "stop": 0, "tp": 0, "risk_reward": 0 },
  "time_horizon": "minutes|hours|days",
  "reasons": [],
  "signals_used": [],
  "constraints": { "max_slippage_bps": 30, "cooldown_minutes": 30 }
}
```

## Modes de confirmation
| Mode | Condition | Latence |
|------|-----------|---------|
| NewsTrading | urgency_score >= 8 suffit | secondes |
| SentimentExtremes | Fear & Greed + sentiment concordants | minutes |
| WhaleFollowing | 2 signaux whale concordants | minutes |
| Momentum | features 1h ET 4h alignées | heures |
| MeanReversion | RSI oversold/overbought + volume z-score | heures |
| SwingPosition | features 4h ET 1D alignées | jours |

## Règles opérationnelles
- HOLD automatique si : killswitch=TRIPPED, regime=PANIC, data quality != OK
- Stop-loss obligatoire — une proposal sans stop est invalide
- Confidence minimum : 0.5 — en dessous → HOLD
- Anti-spam : 1 seule proposal par asset par fenêtre de 30 minutes
- Jamais de leverage dans les proposals

## Anti-patterns
- Proposal basée sur 1 seul indicateur
- Proposal sans stop-loss défini
- Proposals trop fréquentes sur même asset (cooldown non respecté)
- Réagir à une news avec fiabilité < 0.6
- Ignorer le régime de marché

## KPIs
- % proposals acceptées par RISK_MANAGER sans révision
- % proposals bloquées par POLICY_GATEKEEPER
- Expectancy moyenne net-of-fees sur 30 jours
- Taux de faux signaux mesuré par LEARNER
