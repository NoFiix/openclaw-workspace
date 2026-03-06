/**
 * MARKET_EYE v2 — Handler
 * Calcule les indicateurs techniques sur 3 timeframes : 1m, 1h, 4h
 * Émet : trading.intel.market.features (un event par symbol par timeframe)
 * Pas de LLM. Pure maths.
 */

const BINANCE_BASE = "https://api.binance.com";
const SYMBOLS      = ["BTCUSDT", "ETHUSDT", "BNBUSDT"];
const TIMEFRAMES   = [
  { interval: "1m",  limit: 100, label: "1m"  },
  { interval: "1h",  limit: 100, label: "1h"  },
  { interval: "4h",  limit: 100, label: "4h"  },
];
const TIMEOUT_MS   = 8000;

// ─── Fetch ─────────────────────────────────────────────────────────────────

async function fetchOHLCV(symbol, interval, limit) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const url = `${BINANCE_BASE}/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`;
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await res.json();
    return raw.map(k => ({
      open_time:  k[0],
      open:       parseFloat(k[1]),
      high:       parseFloat(k[2]),
      low:        parseFloat(k[3]),
      close:      parseFloat(k[4]),
      volume:     parseFloat(k[5]),
      close_time: k[6],
    }));
  } finally {
    clearTimeout(timer);
  }
}

// ─── Indicateurs ──────────────────────────────────────────────────────────

function calcRSI(closes, period = 14) {
  if (closes.length < period + 1) return null;
  let gains = 0, losses = 0;
  for (let i = closes.length - period; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) gains += diff; else losses -= diff;
  }
  const avgGain = gains / period;
  const avgLoss = losses / period;
  if (avgLoss === 0) return 100;
  return parseFloat((100 - 100 / (1 + avgGain / avgLoss)).toFixed(2));
}

function calcEMA(values, period) {
  if (values.length < period) return null;
  const k = 2 / (period + 1);
  let ema = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < values.length; i++) ema = values[i] * k + ema * (1 - k);
  return ema;
}

function calcBollinger(closes, period = 20, mult = 2) {
  if (closes.length < period) return null;
  const slice = closes.slice(-period);
  const mid   = slice.reduce((a, b) => a + b, 0) / period;
  const std   = Math.sqrt(slice.reduce((a, b) => a + Math.pow(b - mid, 2), 0) / period);
  return {
    upper: parseFloat((mid + mult * std).toFixed(4)),
    mid:   parseFloat(mid.toFixed(4)),
    lower: parseFloat((mid - mult * std).toFixed(4)),
    std:   parseFloat(std.toFixed(6)),
    pct_b: parseFloat(((closes[closes.length-1] - (mid - mult*std)) / (2 * mult * std)).toFixed(3)),
  };
}

function calcATR(candles, period = 14) {
  if (candles.length < period + 1) return null;
  const trs = [];
  for (let i = 1; i < candles.length; i++) {
    const { high, low } = candles[i];
    const prevClose = candles[i - 1].close;
    trs.push(Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose)));
  }
  return parseFloat((trs.slice(-period).reduce((a, b) => a + b, 0) / period).toFixed(6));
}

function calcMACD(closes, fast = 12, slow = 26, signal = 9) {
  if (closes.length < slow + signal) return null;
  const macdValues = [];
  for (let i = slow; i <= closes.length; i++) {
    const ef = calcEMA(closes.slice(0, i), fast);
    const es = calcEMA(closes.slice(0, i), slow);
    if (ef !== null && es !== null) macdValues.push(ef - es);
  }
  const macdLine   = macdValues[macdValues.length - 1];
  const signalLine = calcEMA(macdValues, signal) ?? macdLine;
  return {
    macd:      parseFloat(macdLine.toFixed(6)),
    signal:    parseFloat(signalLine.toFixed(6)),
    histogram: parseFloat((macdLine - signalLine).toFixed(6)),
  };
}

function calcVolumeZScore(volumes, period = 20) {
  if (volumes.length < period) return null;
  const slice = volumes.slice(-period);
  const mean  = slice.reduce((a, b) => a + b, 0) / period;
  const std   = Math.sqrt(slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / period);
  if (std === 0) return 0;
  return parseFloat(((volumes[volumes.length - 1] - mean) / std).toFixed(3));
}

function calcReturns(closes) {
  if (closes.length < 2) return null;
  const last = closes[closes.length - 1];
  const pct  = (n) => closes.length >= n
    ? parseFloat(((last - closes[closes.length - n]) / closes[closes.length - n] * 100).toFixed(4))
    : null;
  return { "1":  pct(2), "5":  pct(6), "15": pct(16), "60": pct(61) };
}

// Trend strength via slope EMA20 vs EMA50
function calcTrendStrength(closes) {
  if (closes.length < 50) return null;
  const ema20 = calcEMA(closes, 20);
  const ema50 = calcEMA(closes, 50);
  if (ema20 === null || ema50 === null) return null;
  const pct = (ema20 - ema50) / ema50 * 100;
  return parseFloat(pct.toFixed(4));
}

// ─── Handler ──────────────────────────────────────────────────────────────

export async function handler(ctx) {
  for (const symbol of SYMBOLS) {
    for (const tf of TIMEFRAMES) {
      try {
        const candles = await fetchOHLCV(symbol, tf.interval, tf.limit);
        if (!candles || candles.length < 30) {
          ctx.log(`${symbol}/${tf.label}: pas assez de bougies (${candles?.length ?? 0}), skip`);
          continue;
        }

        const closes  = candles.map(c => c.close);
        const volumes = candles.map(c => c.volume);
        const price   = closes[closes.length - 1];

        const rsi     = calcRSI(closes, 14);
        const bb      = calcBollinger(closes, 20, 2);
        const atr     = calcATR(candles, 14);
        const macd    = calcMACD(closes);
        const volZ    = calcVolumeZScore(volumes, 20);
        const returns = calcReturns(closes);
        const trend   = calcTrendStrength(closes);

        const features = {
          symbol,
          timeframe:      tf.label,
          price:          parseFloat(price.toFixed(4)),
          returns,
          rsi_14:         rsi,
          bb_upper:       bb?.upper       ?? null,
          bb_lower:       bb?.lower       ?? null,
          bb_mid:         bb?.mid         ?? null,
          bb_std:         bb?.std         ?? null,
          bb_pct_b:       bb?.pct_b       ?? null,
          atr_14:         atr,
          macd:           macd?.macd      ?? null,
          macd_signal:    macd?.signal    ?? null,
          macd_histogram: macd?.histogram ?? null,
          volume_zscore:  volZ,
          trend_strength: trend,
          candles_used:   candles.length,
        };

        ctx.emit(
          "trading.intel.market.features",
          "intel.market.features.v2",
          { asset: symbol, timeframe: tf.label },
          features
        );

        ctx.log(
          `${symbol}/${tf.label} price=${price.toFixed(2)} ` +
          `RSI=${rsi ?? "?"} ` +
          `BB_pctB=${bb?.pct_b ?? "?"} ` +
          `ATR=${atr ?? "?"} ` +
          `MACD=${macd?.histogram?.toFixed(4) ?? "?"} ` +
          `volZ=${volZ ?? "?"} ` +
          `trend=${trend ?? "?"}`
        );

      } catch (e) {
        ctx.log(`⚠️ ${symbol}/${tf.label}: ${e.message}`);
      }
    }
  }
}
