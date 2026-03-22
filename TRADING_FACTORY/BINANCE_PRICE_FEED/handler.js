/**
 * BINANCE_PRICE_FEED — Handler
 * Récupère les données de marché via l'API REST Binance (native fetch Node.js v22).
 * Émet : trading.raw.market.ticker + trading.raw.market.ohlcv
 * Pas de LLM. Pas de dépendances externes.
 */

const BINANCE_BASE = "https://api.binance.com";
const SYMBOLS      = ["BTCUSDT", "ETHUSDT", "BNBUSDT"];
const TIMEOUT_MS   = 8000;

async function fetchWithTimeout(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status} — ${url}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

async function fetchTicker(symbol) {
  return fetchWithTimeout(`${BINANCE_BASE}/api/v3/ticker/24hr?symbol=${symbol}`);
}

async function fetchOHLCV(symbol, interval = "1m", limit = 100) {
  const raw = await fetchWithTimeout(
    `${BINANCE_BASE}/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`
  );
  return raw.map(k => ({
    open_time:  k[0],
    open:       parseFloat(k[1]),
    high:       parseFloat(k[2]),
    low:        parseFloat(k[3]),
    close:      parseFloat(k[4]),
    volume:     parseFloat(k[5]),
    close_time: k[6],
  }));
}

export async function handler(ctx) {
  let success = 0;

  for (const symbol of SYMBOLS) {
    try {
      const [ticker, ohlcv] = await Promise.all([
        fetchTicker(symbol),
        fetchOHLCV(symbol, "1m", 100),
      ]);

      // — Ticker event
      ctx.emit(
        "trading.raw.market.ticker",
        "raw.market.ticker.v1",
        { asset: symbol, timeframe: "1m" },
        {
          symbol,
          price:               parseFloat(ticker.lastPrice),
          bid:                 parseFloat(ticker.bidPrice),
          ask:                 parseFloat(ticker.askPrice),
          volume_24h:          parseFloat(ticker.volume),
          quote_volume_24h:    parseFloat(ticker.quoteVolume),
          price_change_pct_24h:parseFloat(ticker.priceChangePercent),
          high_24h:            parseFloat(ticker.highPrice),
          low_24h:             parseFloat(ticker.lowPrice),
          trades_24h:          ticker.count,
        }
      );

      // — OHLCV event DÉSACTIVÉ (200MB/jour pour rien — MARKET_EYE fetch directement Binance)
      // ctx.emit(
      //   "trading.raw.market.ohlcv",
      //   "raw.market.ohlcv.v1",
      //   { asset: symbol, timeframe: "1m" },
      //   { symbol, interval: "1m", candles: ohlcv }
      // );

      ctx.log(
        `${symbol} price=${ticker.lastPrice} ` +
        `bid=${ticker.bidPrice} ask=${ticker.askPrice} ` +
        `vol=${parseFloat(ticker.volume).toFixed(2)} candles=${ohlcv.length}`
      );
      success++;

    } catch (e) {
      ctx.log(`⚠️ ERREUR ${symbol}: ${e.message}`);
    }
  }

  ctx.log(`✅ ${success}/${SYMBOLS.length} symbols récupérés`);
}
