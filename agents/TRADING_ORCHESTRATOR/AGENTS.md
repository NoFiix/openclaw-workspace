# AGENTS — TRADING_ORCHESTRATOR

## Objectif

Corréler order.plan + policy.decision et orchestrer l'exécution.
Zéro LLM. Logique d'état pure.

## Inputs

- `trading.strategy.order.plan`
- `trading.strategy.policy.decision`

## Output

- `trading.exec.order.submit`

## États du pipeline

| État | Condition |
|---|---|
| PENDING_POLICY | order.plan reçu, attend policy.decision |
| APPROVED | policy APPROVED → submit envoyé |
| BLOCKED | policy BLOCKED |
| PENDING_HUMAN | policy HUMAN_APPROVAL_REQUIRED |
| EXECUTED | submit envoyé à executor |
| EXPIRED | TTL 10min dépassé |

## Logique de corrélation

1. Lire nouveaux order.plans → stocker en PENDING_POLICY
2. Lire nouvelles policy.decisions → corréler via order_plan_ref
3. Pour chaque plan en PENDING_POLICY avec policy trouvée :
   - APPROVED → émettre order.submit → passer en EXECUTED
   - BLOCKED → logger → archiver
   - HUMAN_APPROVAL_REQUIRED → notifier Telegram → passer en PENDING_HUMAN
4. Expirer les plans > 10 min sans résolution

## Payload order.submit
```json
{
  "order_plan_ref": "event_id",
  "policy_decision_ref": "event_id",
  "symbol": "ETHUSDT",
  "side": "BUY",
  "strategy_id": "MeanReversion",
  "variant_id": "A",
  "experiment_id": null,
  "setup": {
    "entry": 2450, "stop": 2380, "tp": 2590,
    "qty": 0.04, "value_usd": 98
  },
  "env": "paper",
  "submitted_at": 0
}
```

## Règles absolues

- jamais soumettre sans policy APPROVED
- idempotence : un order_plan_ref ne soumet qu'une seule fois
- toujours logger chaque transition d'état
- TTL 10 min → EXPIRED si pas de résolution

## Fréquence

- poll 10s, jitter 2s
- zéro coût token

## KPI

- temps moyen proposal → submit
- taux EXPIRED
- taux PENDING_HUMAN non résolus
