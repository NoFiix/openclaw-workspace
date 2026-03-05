/**
 * PREDICTOR Niveau A — Handler
 * Scoring directionnel pondéré sur les features MARKET_EYE.
 * Émet : trading.intel.prediction
 * Pas de LLM. Zéro dépendance externe.
 *
 * Poids :
 *   RSI oversold/overbought  → 0.5
 *   Bollinger band touch     → 0.5
 *   Volume spike             → 1.0
 *   MACD cross               → 1.0
 *   (Regime confirmation     → 1.0 — ajouté en Sprint 2 quand REGIME_DETECTOR tourne)
 *
 * direction_prob = bull_score / (bull_score + bear_score)
 * confidence     = max(bull,bear) / 4.0  (max score possible sans regime = 3.0)
 */

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"];

export async function handler(ctx) {
  for (const symbol of SYMBOLS) {
    const cursorKey = `features_${symbol}`;
    const cursor    = ctx.state.cursors[cursorKey] ?? 0;
    const { events, nextCursor } = ctx.bus.readSince("trading.intel.market.features", cursor, 20);

    const symbolEvents = events.filter(e => e.payload?.symbol === symbol);
    if (symbolEvents.length === 0) continue;
    ctx.state.cursors[cursorKey] = nextCursor;

    const f = symbolEvents[symbolEvents.length - 1].payload;
    let bullScore = 0, bearScore = 0;
    const signals_used    = [];
    const signals_skipped = [];

    // ── RSI (poids 0.5) ───────────────────────────────────────────────
    if (f.rsi_14 !== null) {
      if (f.rsi_14 < 30) {
        bullScore += 0.5;
        signals_used.push(`rsi_oversold(${f.rsi_14})`);
      } else if (f.rsi_14 > 70) {
        bearScore += 0.5;
        signals_used.push(`rsi_overbought(${f.rsi_14})`);
      }
    } else {
      signals_skipped.push("rsi_null");
    }

    // ── Bollinger Bands (poids 0.5) ───────────────────────────────────
    if (f.bb_lower !== null && f.price !== null) {
      if (f.price < f.bb_lower) {
        bullScore += 0.5;
        signals_used.push(`bb_lower_touch(price=${f.price},lower=${f.bb_lower})`);
      } else if (f.price > f.bb_upper) {
        bearScore += 0.5;
        signals_used.push(`bb_upper_touch(price=${f.price},upper=${f.bb_upper})`);
      }
    } else {
      signals_skipped.push("bb_null");
    }

    // ── Volume spike (poids 1.0) ──────────────────────────────────────
    if (f.volume_zscore !== null) {
      if (f.volume_zscore > 2.0) {
        // Direction : si MACD positif ou RSI < 50 → bullish spike
        const bullishContext = (f.macd !== null && f.macd > 0) ||
                               (f.rsi_14 !== null && f.rsi_14 < 50);
        if (bullishContext) {
          bullScore += 1.0;
          signals_used.push(`volume_spike_bull(z=${f.volume_zscore})`);
        } else {
          bearScore += 1.0;
          signals_used.push(`volume_spike_bear(z=${f.volume_zscore})`);
        }
      }
    } else {
      signals_skipped.push("volume_zscore_null");
    }

    // ── MACD cross (poids 1.0) ────────────────────────────────────────
    if (f.macd !== null && f.macd_signal !== null) {
      if (f.macd > f.macd_signal) {
        bullScore += 1.0;
        signals_used.push(`macd_bullish(${f.macd.toFixed(4)}>${f.macd_signal.toFixed(4)})`);
      } else if (f.macd < f.macd_signal) {
        bearScore += 1.0;
        signals_used.push(`macd_bearish(${f.macd.toFixed(4)}<${f.macd_signal.toFixed(4)})`);
      }
    } else {
      signals_skipped.push("macd_null");
    }

    // ── Calcul final ─────────────────────────────────────────────────
    const total         = bullScore + bearScore;
    const direction_prob = total > 0
      ? parseFloat((bullScore / total).toFixed(3))
      : 0.5;
    // Max score possible sans regime = 3.0 (RSI+BB+Volume+MACD sans regime)
    const confidence = parseFloat((Math.max(bullScore, bearScore) / 3.0).toFixed(3));

    const direction = direction_prob > 0.60 ? "🟢 BULL"
                    : direction_prob < 0.40 ? "🔴 BEAR"
                    : "⚪ NEUTRAL";

    ctx.emit(
      "trading.intel.prediction",
      "intel.prediction.v1",
      { asset: symbol, timeframe: "1m" },
      {
        symbol,
        direction_prob,
        confidence,
        bull_score:     parseFloat(bullScore.toFixed(1)),
        bear_score:     parseFloat(bearScore.toFixed(1)),
        model_type:     "statistical_v1",
        signals_used,
        signals_skipped,
        horizon:        "1h",
        price:          f.price,
        rsi:            f.rsi_14,
        atr:            f.atr_14,
      }
    );

    ctx.log(
      `${symbol} ${direction} ` +
      `prob=${direction_prob} conf=${confidence} ` +
      `bull=${bullScore} bear=${bearScore} ` +
      `signals=[${signals_used.join(" | ")}]`
    );
  }
}
