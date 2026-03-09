# AGENTS — POLICY_ENGINE

## Objectif

Vérifier qu'un order.plan respecte toutes les règles du système.
Produire une décision claire : APPROVED / BLOCKED / HUMAN_APPROVAL_REQUIRED.
Zéro LLM. Logique de règles pure.

## Input

- `trading.strategy.order.plan`

## Output

- `trading.strategy.policy.decision`

## Décisions possibles

| Décision | Condition |
|---|---|
| APPROVED | toutes les règles passent |
| BLOCKED | au moins une règle échoue |
| HUMAN_APPROVAL_REQUIRED | notional > seuil config |

## Checks effectués (dans l'ordre)

1. kill switch → BLOCKED si TRIPPED
2. asset dans allowed_assets → BLOCKED sinon
3. asset non blacklisté → BLOCKED sinon
4. stratégie dans allowed_strategies → BLOCKED sinon
5. env cohérent (paper/live) → BLOCKED sinon
6. plage horaire autorisée → BLOCKED sinon (si activé)
7. notional < seuil → HUMAN_APPROVAL_REQUIRED sinon
8. A/B testing → enrichit variant_id/experiment_id

## Payload policy.decision
```json
{
  "order_plan_ref": "event_id",
  "symbol": "ETHUSDT",
  "side": "BUY",
  "strategy_id": "MeanReversion",
  "variant_id": "A",
  "experiment_id": null,
  "decision": "APPROVED",
  "reason": "all_policies_passed",
  "requires_human_approval": false,
  "policy_version": "2026-03-09-v1",
  "checks": {
    "killswitch_armed": true,
    "asset_allowed": true,
    "not_blacklisted": true,
    "strategy_allowed": true,
    "env_allowed": true,
    "time_window_allowed": true,
    "notional_below_threshold": true
  },
  "decided_at": 0
}
```

## Règles absolues

- jamais approuver si kill switch TRIPPED
- jamais approuver un asset absent de allowed_assets
- toujours loguer la raison du blocage
- toujours référencer order_plan_ref

## KPI

- taux d'approbation vs blocage
- raisons de blocage les plus fréquentes
- décisions HUMAN_APPROVAL_REQUIRED non résolues

## Fréquence

- poll 30s, jitter 5s
- zéro coût token
