# integrations_externes.md — Services externes

**Date** : 2026-03-15
**Méthode** : `grep` sur les URLs dans le code source + analyse des `.env`

---

## POLY_FACTORY — Services externes (Python)

| Service | URL | Usage | Credentials | Type | Tag |
|---------|-----|-------|-------------|------|-----|
| Polymarket Gamma API | `https://gamma-api.polymarket.com` | Marchés, prix, orderbooks | Aucun (API publique) | TYPE_1 | [OBSERVÉ] |
| Polymarket CLOB API | `https://clob.polymarket.com` | Trading (place_order, get_trades) | `POLYMARKET_API_KEY`, `POLYMARKET_API_SECRET`, `WALLET_PRIVATE_KEY` | TYPE_1 | [OBSERVÉ] |
| Binance REST API | `https://api.binance.com` | Prix crypto (BTC, ETH) | `BINANCE_API_KEY`, `BINANCE_API_SECRET` | TYPE_1 | [OBSERVÉ] |
| NOAA Weather API | `https://api.weather.gov/points/`, `https://api.weather.gov/stations/` | Prévisions météo | Aucun (API publique) | TYPE_2 | [OBSERVÉ] |
| Kalshi Trading API | `https://trading-api.kalshi.com/trade-api/v2` | Marchés Kalshi (connecteur) | [INCONNU] | TYPE_1 | [OBSERVÉ] |
| The Odds API | `https://api.the-odds-api.com/v4` | Cotes sportives (connecteur) | [INCONNU] | TYPE_2 | [OBSERVÉ] |

---

## Trading Factory JS — Services externes

| Service | URL | Usage | Type | Tag |
|---------|-----|-------|------|-----|
| Binance API | `https://api.binance.com` | Prix crypto | TYPE_1 | [OBSERVÉ] |
| Binance Testnet | `https://testnet.binance.vision` | Tests | TYPE_3 | [OBSERVÉ] |
| CoinGecko | `https://api.coingecko.com/api/v3/simple/price` | Prix ETH/BTC | TYPE_2 | [OBSERVÉ] |
| Etherscan | `https://api.etherscan.io/v2/api` | Données blockchain | TYPE_2 | [OBSERVÉ] |
| CryptoPanic | `https://cryptopanic.com/api/v1/posts/` | News crypto | TYPE_3 | [OBSERVÉ] |
| Fear & Greed Index | `https://api.alternative.me/fng/` | Sentiment | TYPE_3 | [OBSERVÉ] |
| Telegram API | `https://api.telegram.org` | Notifications | TYPE_2 | [OBSERVÉ] |
| Twitter/X API | `https://api.twitter.com/2/tweets` | Publication | TYPE_3 | [OBSERVÉ] |
| YouTube Data API | `https://www.googleapis.com/youtube/v3/` | Contenu | TYPE_3 | [OBSERVÉ] |

---

## Content Factory — Services externes (RSS/scraping)

| Service | URL | Usage | Type | Tag |
|---------|-----|-------|------|-----|
| CoinDesk RSS | `https://www.coindesk.com/arc/outboundfeeds/rss` | News | TYPE_3 | [OBSERVÉ] |
| CoinTelegraph RSS | `https://cointelegraph.com/rss` | News | TYPE_3 | [OBSERVÉ] |
| Bitcoin Magazine RSS | `https://bitcoinmagazine.com/feed` | News | TYPE_3 | [OBSERVÉ] |
| Decrypt RSS | `https://decrypt.co/feed` | News | TYPE_3 | [OBSERVÉ] |
| The Defiant | `https://thedefiant.io/feed` | News | TYPE_3 | [OBSERVÉ] |
| CryptoAst RSS | `https://cryptoast.fr/feed/` | News (FR) | TYPE_3 | [OBSERVÉ] |
| Journal du Coin RSS | `https://journalducoin.com/feed/` | News (FR) | TYPE_3 | [OBSERVÉ] |
| SEC EDGAR | `https://efts.sec.gov/LATEST/search-index` | Réglementaire | TYPE_3 | [OBSERVÉ] |
| Anthropic API | `https://api.anthropic.com/v1/messages` | LLM (analyse) | TYPE_2 | [OBSERVÉ] |

---

## Credentials (.env)

### POLY_FACTORY/.env

| Clé | Présente | Nécessaire pour | Tag |
|-----|----------|-----------------|-----|
| `POLYMARKET_API_KEY` | Oui | CLOB trading | [OBSERVÉ] |
| `POLYMARKET_API_SECRET` | Oui | CLOB trading | [OBSERVÉ] |
| `POLYMARKET_API_PASSPHRASE` | Oui | CLOB trading | [OBSERVÉ] |
| `POLYMARKET_WALLET_ADDRESS` | Oui | Wallet tracking | [OBSERVÉ] |
| `METAMASK_PRIVATE_KEY` | Oui | [INCONNU] usage exact | [OBSERVÉ] |
| `BINANCE_API_KEY` | Oui | Feed Binance | [OBSERVÉ] |
| `BINANCE_API_SECRET` | Oui | Feed Binance | [OBSERVÉ] |
| `POLYGON_RPC_URL` | Oui | On-chain queries | [OBSERVÉ] |
| `ANTHROPIC_API_KEY` | Oui | LLM calls | [OBSERVÉ] |
| `WALLET_PRIVATE_KEY` | **Absent** | `_get_clob_client()` | [OBSERVÉ] |

**Risque** [DÉDUIT] : `WALLET_PRIVATE_KEY` est requis par `connector_polymarket._get_clob_client()` (ligne 257) mais absent du `.env`. Le code crashera si `place_order()` ou `get_positions()` est appelé en mode live.

### dashboard/api/.env

| Clé | Usage | Tag |
|-----|-------|-----|
| `DASHBOARD_API_KEY` | Auth API | [OBSERVÉ] |
| `ALLOWED_ORIGIN` | CORS (dupliqué 2×) | [OBSERVÉ] |
| `STATE_DIR` | Chemin state | [OBSERVÉ] |
| `WORKSPACE_DIR` | Chemin workspace | [OBSERVÉ] |
| `AGGREGATES_DIR` | Chemin aggregates | [OBSERVÉ] |
| `POLY_BASE_PATH` | Bridge vers POLY_FACTORY state | [OBSERVÉ] |
