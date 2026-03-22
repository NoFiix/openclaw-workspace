# Memory — TRADE_STRATEGY_TUNER

Historique complet des versions de chaque stratégie optimisée.

Objectifs :
- suivre l'évolution des paramètres
- tracer chaque hypothèse testée
- permettre un rollback automatique
- éviter de retester les mêmes changements (anti-oscillation)

Fichier principal : strategy_versions.json (dans state/trading/learning/)

## Structure

{
  "MeanReversion": {
    "current_version": 2,
    "best_version": 2,
    "versions": [
      {
        "v": 1,
        "params": { "rsi_low": 35, "rsi_high": 65 },
        "trades": 30,
        "trades_since_last_version": 30,
        "score": 0.45,
        "hypothesis": "RSI trop permissif, entrées trop tôt",
        "param_changed": "rsi_low",
        "change": { "from": 35, "to": 32 },
        "expected_effect": "Moins de faux positifs en régime RANGE",
        "confidence": "medium",
        "regime_dominant": "RANGE",
        "applied_at": "2026-03-10"
      }
    ]
  }
}

## Règles de lecture

- current_version != best_version → rollback possible
- trades_since_last_version < 10 → itération non significative
- regime_dominant → contextualise les résultats
