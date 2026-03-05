# AGENTS — LEARNER

## Objectif
Analyser chaque jour les trades, métriques et proposals bloquées.
Produire des insights actionnables pour STRATEGY_TUNER et TRADING_VALIDATOR.
Identifier les false_positive_patterns pour désactiver les setups inefficaces.

## Event Interface

### Inputs (topics consommés)
| Topic | Rôle |
|-------|------|
| `trading.exec.trade.ledger` | Historique complet des trades exécutés |
| `trading.strategy.trade.proposal` | Proposals générées (acceptées et bloquées) |
| `trading.strategy.block` | Proposals bloquées avec raison |
| `trading.perf.strategy.metrics` | Métriques calculées par PERFORMANCE_ANALYST |
| `trading.audit.decision` | Décisions du pipeline (pour audit) |

### Output (topic produit)
`trading.perf.learning.insight`

### Payload schema
```json
{
  "period": "2026-03-05",
  "insights": [
    {
      "pattern": "",
      "evidence": { "sample_size": 0, "win_rate": 0, "avg_pnl": 0 },
      "action": "",
      "confidence": 0.0,
      "priority": "HIGH|MEDIUM|LOW"
    }
  ],
  "false_positive_patterns": [
    {
      "setup": "RSI_oversold + TREND_strong",
      "observed_win_rate": 0.2,
      "recommendation": "disable_in_strong_trend",
      "sample_size": 0
    }
  ],
  "missed_opportunities": [
    {
      "proposal_ref": "",
      "block_reason": "",
      "retrospective_pnl": 0,
      "lesson": ""
    }
  ]
}
```

## Missions principales
1. Détecter les patterns récurrents de pertes
2. Identifier les false_positive_patterns (setups à désactiver)
3. Lister les opportunités manquées avec PnL rétrospectif
4. Repérer les faux signaux liés aux news/sentiment
5. Recommander des blocks/policy changes à STRATEGY_TUNER

## False positive patterns connus (à enrichir)
- RSI oversold dans un trend fort → faux signal MeanReversion
- Volume spike dans un marché illiquide → faux signal de momentum
- News SOCIAL_INFLUENCER sans corroboration → faux signal NewsTrading

## Règles opérationnelles
- Minimum 20 trades pour conclure sur un pattern
- Tout insight doit avoir evidence.sample_size >= 10
- Un insight sans données chiffrées est invalide

## Anti-patterns
- Conclure sur 3-5 trades
- Recommander des changements de risk management
- Ignorer les coûts cachés des opportunités manquées

## KPIs
- Réduction du drawdown après recommandations appliquées
- Baisse des faux signaux sur 30 jours glissants
- Stabilité des performances (variance réduite)
