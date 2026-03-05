# AGENTS — PERFORMANCE_ANALYST

## Objectif
Calculer chaque jour les métriques de performance du système.
Produire un rapport quotidien Telegram et des métriques hebdomadaires pour DARWIN_SELECTOR.
Alerter immédiatement si drawdown journalier > 2% (seuil avant kill switch à 3%).

## Event Interface

### Inputs (topics consommés)
| Topic | Rôle |
|-------|------|
| `trading.exec.trade.ledger` | Historique complet des trades |
| `trading.exec.position.snapshot` | Positions ouvertes actuelles |
| `trading.intel.regime` | Contexte de marché pour breakdown |

### Outputs (topics produits)
| Topic | Fréquence |
|-------|-----------|
| `trading.perf.strategy.metrics` | Quotidien |
| `trading.perf.daily.report` | Quotidien |
| `trading.perf.weekly.report` | Hebdomadaire |
| `trading.ops.alert` | Si drawdown > 2% en 24h |

### Payload schema (strategy.metrics)
```json
{
  "period": "2026-03-05",
  "env": "paper|live",
  "by_strategy": {
    "Momentum": {
      "trades": 0, "win_rate": 0, "profit_factor": 0,
      "sharpe": 0, "max_drawdown": 0, "expectancy": 0,
      "avg_hold_minutes": 0, "total_pnl_usd": 0
    }
  },
  "global": {
    "total_trades": 0, "win_rate": 0, "total_pnl_usd": 0,
    "max_drawdown_24h": 0, "best_trade": 0, "worst_trade": 0
  },
  "benchmarks": {
    "hold_btc_pct": 0,
    "dca_pct": 0,
    "system_pct": 0,
    "beats_benchmark": false
  }
}
```

## Seuils d'alerte
| Seuil | Action |
|-------|--------|
| Drawdown > 2% en 24h | Alert Telegram — "Attention seuil kill switch proche" |
| Drawdown > 3% en 24h | Kill switch déclenché par KILL_SWITCH_GUARDIAN |
| Win rate < 35% sur 20+ trades | Mention dans rapport — candidat désactivation |
| 0 trades en 48h | Vérification système — possible bug TRADE_GENERATOR |

## Format rapport Telegram daily
```
📊 *Rapport Daily — CryptoRizon Trading*
📅 [DATE] | 🌍 [ENV: paper/live]

💰 PnL net : [+/-X.XX%] | [+/-$XX]
📈 Win rate : XX% ([N] trades)
📉 Max drawdown 24h : X.XX%
🏆 Meilleure strat : [NOM] ([+X%])

🔴 Points d'attention : [si anomalie]
📊 vs Hold BTC : [+/-X%]
```

## Anti-patterns
- Mélanger données paper et live
- Conclure sur < 10 trades
- Omettre la comparaison benchmark
- Ne pas alerter si drawdown > 2%

## KPIs
- Uplift mesuré sur les stratégies après recommandations appliquées
- Précision des alertes précoces (drawdown 2% → kill switch 3%)
