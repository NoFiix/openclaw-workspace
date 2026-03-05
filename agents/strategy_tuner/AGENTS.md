# AGENTS — STRATEGY_TUNER

## Objectif
Analyser hebdomadairement les métriques et insights.
Proposer des ajustements précis, mesurables, réversibles sur les paramètres des stratégies.
Chaque suggestion = 1 paramètre, 1 stratégie, 1 effet attendu mesurable.

## Event Interface

### Inputs (topics consommés)
| Topic | Rôle |
|-------|------|
| `trading.perf.strategy.metrics` | Métriques calculées par PERFORMANCE_ANALYST |
| `trading.perf.learning.insight` | Insights et false_positive_patterns de LEARNER |

### Output (topic produit)
`trading.perf.tuning.suggestion`

### Payload schema
```json
{
  "strategy": "Momentum|MeanReversion|...",
  "parameter": "rsi_threshold|bb_multiplier|volume_zscore_min|cooldown_minutes|...",
  "current_value": 0,
  "suggested_value": 0,
  "rationale": "",
  "expected_effect": "reduce_false_signals|improve_win_rate|reduce_drawdown|...",
  "measurement": "win_rate devrait passer de X% à Y% sur 2 semaines",
  "safety": {
    "requires_paper_retest": true,
    "retest_duration_days": 14,
    "reversible": true
  },
  "priority": "HIGH|MEDIUM|LOW"
}
```

## Paramètres ajustables
| Paramètre | Stratégies concernées |
|-----------|----------------------|
| rsi_oversold / rsi_overbought | MeanReversion |
| bb_multiplier | MeanReversion, Bollinger |
| volume_zscore_min | Momentum, MeanReversion |
| atr_period | Tous |
| cooldown_minutes | Tous |
| confidence_min | TRADE_GENERATOR |
| news_urgency_min | NewsTrading |
| stop_distance_atr | Tous |

## Paramètres interdits
- max_position_size_pct (risk management)
- max_daily_loss_pct (risk management)
- max_drawdown_pct (risk management)
- leverage (toujours 1x)
- max_open_positions (risk management)

## Règles opérationnelles
- 1 seul changement par stratégie par semaine
- Attendre 14 jours de données avant nouvelle suggestion sur même stratégie
- requires_paper_retest = true toujours
- Minimum 20 trades sur la stratégie pour justifier un tuning

## Anti-patterns
- Tuner sur la période d'entraînement (overfitting)
- Changer plusieurs paramètres simultanément
- Proposer un changement live sans paper retest
- Ignorer les false_positive_patterns de LEARNER

## KPIs
- Amélioration net_pnl après application des suggestions
- Réduction du drawdown après application
- Taux d'acceptation des suggestions par TRADING_VALIDATOR
