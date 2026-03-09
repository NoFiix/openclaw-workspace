# AGENTS — WHALE_FEED

## Objectif

Collecter et normaliser les événements whales bruts depuis les sources externes.
Aucun LLM. Aucun coût token. Logique pure.

## Sources actives (Sprint 1)

### Etherscan API
- gros transferts ETH natifs
- gros transferts ERC20 : USDT, USDC, WBTC
- lookback : 25 blocs (~5 minutes) par run

### CoinGecko / GeckoTerminal
- désactivé Sprint 1
- activable Sprint 2 via config

## Outputs

- `trading.raw.whale.transfer`
- `trading.raw.whale.dex_trade` (Sprint 2)

## Format — whale.transfer
```json
{
  "chain": "ethereum",
  "asset": "ETH",
  "token_address": null,
  "tx_hash": "0xabc",
  "block_number": 22001234,
  "from": "0xfrom",
  "to": "0xto",
  "amount": 1250.5,
  "amount_usd": 4120000,
  "detected_at": "2026-03-09T12:00:00Z",
  "source": "etherscan",
  "raw_type": "native_transfer"
}
```

## Règles absolues

- jamais publier deux fois le même tx_hash
- jamais publier sous les seuils config
- jamais interpréter ou scorer

## Déduplication

- par tx_hash + source + asset
- TTL 2h (on ne garde que les hashes des 2 dernières heures)
- pas de tableau infini

## Seuils Sprint 1

- ETH >= 500 000 USD
- WBTC >= 500 000 USD
- USDT >= 1 000 000 USD
- USDC >= 1 000 000 USD

## Fréquence

- 1x/heure (3600s) — vision tendance, pas tick-by-tick
- zéro coût token

## KPI

- événements valides publiés par run
- taux de doublons évités
- taux d'erreurs API
