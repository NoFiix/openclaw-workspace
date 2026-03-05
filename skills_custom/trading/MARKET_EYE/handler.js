/**
 * MARKET_EYE — Handler
 * Calcule les indicateurs techniques sur les données OHLCV.
 * Émet : trading.intel.market.features
 * Pas de LLM. Pure maths.
 */

// ─── Indicateurs techniques ────────────────────────────────────────────────

function calcRSI(closes, period = 14) {
  if (closes.length < period + 1) return null;
  let gains = 0, losses = 0;
  for (let i = closes.length - period; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) gains += diff; else losses -= diff;
  }
  let avgGain = gains / period;
  let avgLoss = losses / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return parseFloat((100 - 100 / (1 + rs)).toFixed(2));
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
    upper: parseFloat((mid + mult * std).toFixed(2)),
    mid:   parseFloat(mid.toFixed(2)),
    lower: parseFloat((mid - mult * std).toFixed(2)),
    std:   parseFloat(std.toFixed(4)),
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
  const atr = trs.slice(-period).reduce((a, b) => a + b, 0) / period;
  return parseFloat(atr.toFixed(4));
}

function calcMACD(closes, fast = 12, slow = 26, signal = 9) {
  if (closes.length < slow + signal) return null;
  const emaFast = calcEMA(closes, fast);
  const emaSlow = calcEMA(closes, slow);
  if (emaFast === null || emaSlow === null) return null;
  const macdLine = emaFast - emaSlow;
  // Signal = EMA(9) du MACD — approximation sur les N derniers points
  const macdValues = [];
  for (let i = slow; i <= closes.length; i++) {
    const ef = calcEMA(closes.slice(0, i), fast);
    const es = calcEMA(closes.slice(0, i), slow);
    if (ef !== null && es !== null) macdValues.push(ef - es);
  }
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
  const get  = (n) => closes.length >= n ? (last - closes[closes.length - n]) / closes[closes.length - n] : null;
  return {
    "1m":  get(2),
    "5m":  get(6),
    "15m": get(16),
    "1h":  get(61),
  };
}

// ─── Handler ───────────────────────────────────────────────────────────────

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"];

export async function handler(ctx) {
  for (const symbol of SYMBOLS) {
    const cursorKey = `ohlcv_${symbol}`;
    const cursor    = ctx.state.cursors[cursorKey] ?? 0;
    const { events, nextCursor } = ctx.bus.readSince("trading.raw.market.ohlcv", cursor, 20);

    const symbolEvents = events.filter(e => e.payload?.symbol === symbol);
    if (symbolEvents.length === 0) continue;
    ctx.state.cursors[cursorKey] = nextCursor;

    const candles = symbolEvents[symbolEvents.length - 1].payload.candles;
    if (!candles || candles.length < 30) {
      ctx.log(`${symbol}: pas assez de bougies (${candles?.length ?? 0}), skip`);
      continue;
    }

    const closes  = candles.map(c => c.close);
    const volumes = candles.map(c => c.volume);
    const price   = closes[closes.length - 1];

    const rsi      = calcRSI(closes, 14);
    const bb       = calcBollinger(closes, 20, 2);
    const atr      = calcATR(candles, 14);
    const macd     = calcMACD(closes);
    const volZ     = calcVolumeZScore(volumes, 20);
    const returns  = calcReturns(closes);

    const features = {
      symbol,
      price:          parseFloat(price.toFixed(2)),
      returns,
      rsi_14:         rsi,
      bb_upper:       bb?.upper  ?? null,
      bb_lower:       bb?.lower  ?? null,
      bb_mid:         bb?.mid    ?? null,
      bb_std:         bb?.std    ?? null,
      atr_14:         atr,
      macd:           macd?.macd      ?? null,
      macd_signal:    macd?.signal    ?? null,
      macd_histogram: macd?.histogram ?? null,
      volume_zscore:  volZ,
      candles_used:   candles.length,
    };

    ctx.emit(
      "trading.intel.market.features",
      "intel.market.features.v1",
      { asset: symbol, timeframe: "1m" },
      features
    );

    ctx.log(
      `${symbol} price=${price.toFixed(2)} ` +
      `RSI=${rsi ?? "?"} ` +
      `BB=[${bb?.lower ?? "?"},${bb?.upper ?? "?"}] ` +
      `ATR=${atr ?? "?"} ` +
      `MACD=${macd?.macd?.toFixed(2) ?? "?"} ` +
      `volZ=${volZ ?? "?"}`
    );
  }
}
