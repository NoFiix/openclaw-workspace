# AGENTS — WHALE_ANALYZER

## Objectif

Transformer les événements whales bruts en signal consultatif par actif.
Aucun LLM. Aucun coût token. Logique pure.

## Inputs

- `trading.raw.whale.transfer`
- `trading.raw.whale.dex_trade` (Sprint 2)

## Output

- `trading.intel.whale.signal`

## Classification des événements

| Type | Interprétation | Score |
|---|---|---|
| TO_EXCHANGE | pression vendeuse potentielle | -0.35 |
| FROM_EXCHANGE | accumulation potentielle | +0.35 |
| STABLE_INFLOW | pouvoir d'achat entrant | +0.25 |
| DEX_WHALE_BUY | biais haussier léger | +0.15 |
| DEX_WHALE_SELL | biais baissier léger | -0.15 |

## Faux signaux filtrés

- exchange → exchange (interne)
- bridge-related
- custody probable
- sous seuil
- doublons

## Score

- whale_flow_score ∈ [-1.0, +1.0]
- fenêtre glissante 6h
- score > 0.30 → BULLISH
- score < -0.30 → BEARISH
- sinon → NEUTRAL

## Payload final
```json
{
  "asset": "ETH",
  "chain": "ethereum",
  "window": "6h",
  "whale_flow_score": 0.42,
  "bias": "BULLISH",
  "confidence": 0.68,
  "components": {
    "to_exchange_count": 1,
    "from_exchange_count": 4,
    "stable_inflow_count": 2,
    "dex_whale_buy_count": 1,
    "dex_whale_sell_count": 0
  },
  "notional_summary_usd": {
    "to_exchange": 1200000,
    "from_exchange": 3400000,
    "stable_inflow": 2100000,
    "dex_buys": 700000,
    "dex_sells": 0
  },
  "entity_labels": {},
  "is_exchange_internal": false,
  "is_bridge_related": false,
  "interpretation": "Net whale accumulation bias on ETH over 6h."
}
```

## Utilisation par TRADE_GENERATOR

- score > 0.30 → +0.07 sur confidence d'un long (max)
- score < -0.30 → -0.07 sur confidence d'un long (max)
- neutre → aucun effet

Signal toujours secondaire. Jamais déclencheur seul.

## Fréquence

- 1x/heure (3600s), jitter +300s (tourne 5min après WHALE_FEED)
- zéro coût token

## KPI

- stabilité du score par actif
- taux de faux positifs filtrés
- utilité comme confluence dans les proposals
