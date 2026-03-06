/**
 * REGIME_DETECTOR — Handler
 * Détermine le régime de marché en croisant les features 1m/1h/4h.
 * Émet : trading.intel.regime
 * Pas de LLM. Logique de règles pure.
 *
 * Régimes possibles :
 *   TREND_UP    — tendance haussière confirmée multi-timeframe
 *   TREND_DOWN  — tendance baissière confirmée multi-timeframe
 *   RANGE       — marché lateral, oscillations dans les BB
 *   PANIC       — crash rapide, volume spike + RSI effondré
 *   EUPHORIA    — rallye extrême, RSI overbought + volume spike
 *   VOLATILE    — forte volatilité sans direction claire
 *   UNKNOWN     — données insuffisantes
 */

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"];

// ─── Règles de détection ──────────────────────────────────────────────────

function detectSymbolRegime(f1m, f1h, f4h) {
  if (!f1m || !f1h || !f4h) return { regime: "UNKNOWN", confidence: 0, reasons: ["données manquantes"] };

  const reasons = [];
  let score_up = 0, score_down = 0;

  // ── PANIC : prioritaire ───────────────────────────────────────────────
  // RSI 1m < 20 + volume spike + prix sous BB lower 1h
  if (
    f1m.rsi_14 !== null && f1m.rsi_14 < 20 &&
    f1m.volume_zscore !== null && f1m.volume_zscore > 2.5 &&
    f1h.bb_pct_b !== null && f1h.bb_pct_b < 0
  ) {
    reasons.push(`PANIC: RSI_1m=${f1m.rsi_14} volZ_1m=${f1m.volume_zscore} BB_1h=${f1h.bb_pct_b}`);
    return { regime: "PANIC", confidence: 0.85, reasons };
  }

  // ── EUPHORIA : prioritaire ────────────────────────────────────────────
  // RSI 1h > 80 + RSI 4h > 75 + volume spike
  if (
    f1h.rsi_14 !== null && f1h.rsi_14 > 80 &&
    f4h.rsi_14 !== null && f4h.rsi_14 > 75 &&
    f1m.volume_zscore !== null && f1m.volume_zscore > 2.0
  ) {
    reasons.push(`EUPHORIA: RSI_1h=${f1h.rsi_14} RSI_4h=${f4h.rsi_14} volZ=${f1m.volume_zscore}`);
    return { regime: "EUPHORIA", confidence: 0.80, reasons };
  }

  // ── TREND signals ─────────────────────────────────────────────────────

  // Trend strength 4h positif = signal haussier fort (poids 2)
  if (f4h.trend_strength !== null) {
    if (f4h.trend_strength > 1.0) {
      score_up += 2;
      reasons.push(`trend_4h_up=${f4h.trend_strength.toFixed(2)}`);
    } else if (f4h.trend_strength < -1.0) {
      score_down += 2;
      reasons.push(`trend_4h_down=${f4h.trend_strength.toFixed(2)}`);
    }
  }

  // MACD histogram 4h direction (poids 1.5)
  if (f4h.macd_histogram !== null) {
    if (f4h.macd_histogram > 0) {
      score_up += 1.5;
      reasons.push(`macd_4h_bull=${f4h.macd_histogram.toFixed(4)}`);
    } else {
      score_down += 1.5;
      reasons.push(`macd_4h_bear=${f4h.macd_histogram.toFixed(4)}`);
    }
  }

  // MACD histogram 1h direction (poids 1)
  if (f1h.macd_histogram !== null) {
    if (f1h.macd_histogram > 0) {
      score_up += 1;
      reasons.push(`macd_1h_bull`);
    } else {
      score_down += 1;
      reasons.push(`macd_1h_bear`);
    }
  }

  // RSI 1h (poids 1)
  if (f1h.rsi_14 !== null) {
    if (f1h.rsi_14 > 55) {
      score_up += 1;
      reasons.push(`rsi_1h=${f1h.rsi_14}`);
    } else if (f1h.rsi_14 < 45) {
      score_down += 1;
      reasons.push(`rsi_1h=${f1h.rsi_14}`);
    }
  }

  // BB pct_b 4h (position dans les bandes — poids 0.5)
  if (f4h.bb_pct_b !== null) {
    if (f4h.bb_pct_b > 0.6) {
      score_up += 0.5;
      reasons.push(`bb_4h_upper=${f4h.bb_pct_b}`);
    } else if (f4h.bb_pct_b < 0.4) {
      score_down += 0.5;
      reasons.push(`bb_4h_lower=${f4h.bb_pct_b}`);
    }
  }

  const total      = score_up + score_down;
  const dominance  = total > 0 ? Math.max(score_up, score_down) / total : 0;

  // ── RANGE : signaux contradictoires ou faibles ────────────────────────
  // Trend 4h faible ET RSI 1h neutre (40-60) ET BB_pctB 4h au milieu
  if (
    Math.abs(f4h.trend_strength ?? 0) < 0.5 &&
    f1h.rsi_14 !== null && f1h.rsi_14 >= 40 && f1h.rsi_14 <= 60 &&
    f4h.bb_pct_b !== null && f4h.bb_pct_b >= 0.3 && f4h.bb_pct_b <= 0.7
  ) {
    return {
      regime:     "RANGE",
      confidence: parseFloat((0.5 + dominance * 0.2).toFixed(2)),
      reasons:    [...reasons, `range: trend_4h=${(f4h.trend_strength??0).toFixed(2)} RSI_1h=${f1h.rsi_14}`],
    };
  }

  // ── VOLATILE : ATR élevé sans direction claire ────────────────────────
  if (dominance < 0.6 && f1m.volume_zscore !== null && f1m.volume_zscore > 1.5) {
    return {
      regime:     "VOLATILE",
      confidence: 0.55,
      reasons:    [...reasons, `volatile: dominance=${dominance.toFixed(2)} volZ=${f1m.volume_zscore}`],
    };
  }

  // ── TREND_UP / TREND_DOWN ─────────────────────────────────────────────
  if (score_up > score_down && dominance >= 0.6) {
    return {
      regime:     "TREND_UP",
      confidence: parseFloat(Math.min(0.95, 0.5 + dominance * 0.5).toFixed(2)),
      reasons,
    };
  }

  if (score_down > score_up && dominance >= 0.6) {
    return {
      regime:     "TREND_DOWN",
      confidence: parseFloat(Math.min(0.95, 0.5 + dominance * 0.5).toFixed(2)),
      reasons,
    };
  }

  return { regime: "RANGE", confidence: 0.45, reasons: [...reasons, "indécis"] };
}

// ─── Agrégation multi-symbols → régime global ────────────────────────────

function aggregateRegimes(symbolRegimes) {
  const votes = {};
  let totalConf = 0;

  for (const { regime, confidence } of symbolRegimes) {
    votes[regime] = (votes[regime] ?? 0) + confidence;
    totalConf += confidence;
  }

  // Régime dominant = celui avec le plus de confidence cumulée
  const dominant = Object.entries(votes)
    .sort(([, a], [, b]) => b - a)[0];

  const globalRegime     = dominant[0];
  const globalConfidence = parseFloat((dominant[1] / totalConf).toFixed(3));

  // Alerte si divergence forte (ex: BTC en TREND_UP mais ETH en PANIC)
  const uniqueRegimes = [...new Set(symbolRegimes.map(r => r.regime))];
  const divergence    = uniqueRegimes.length > 2;

  return { globalRegime, globalConfidence, divergence, votes };
}

// ─── Handler ──────────────────────────────────────────────────────────────

export async function handler(ctx) {
  const symbolRegimes = [];
  const bySymbol      = {};

  for (const symbol of SYMBOLS) {
    // Lire les derniers features pour chaque timeframe depuis le bus
    const get = (tf) => {
      const cursorKey = `features_${symbol}_${tf}`;
      const cursor    = ctx.state.cursors[cursorKey] ?? 0;
      const { events, nextCursor } = ctx.bus.readSince("trading.intel.market.features", cursor, 200);
      const symbolTfEvents = events.filter(
        e => e.payload?.symbol === symbol && e.payload?.timeframe === tf
      );
      if (symbolTfEvents.length > 0) {
        ctx.state.cursors[cursorKey] = nextCursor;
        return symbolTfEvents[symbolTfEvents.length - 1].payload;
      }
      // Fallback : relire depuis le début si curseur vide
      const { events: allEvents } = ctx.bus.readSince("trading.intel.market.features", 0, 5000);
      const filtered = allEvents.filter(
        e => e.payload?.symbol === symbol && e.payload?.timeframe === tf
      );
      return filtered.length > 0 ? filtered[filtered.length - 1].payload : null;
    };

    const f1m = get("1m");
    const f1h = get("1h");
    const f4h = get("4h");

    if (!f1m && !f1h && !f4h) {
      ctx.log(`⚠️ ${symbol}: aucune feature disponible — skip`);
      continue;
    }

    const result = detectSymbolRegime(f1m, f1h, f4h);
    symbolRegimes.push({ symbol, ...result });
    bySymbol[symbol] = result;

    const emoji = {
      TREND_UP: "🟢", TREND_DOWN: "🔴", RANGE: "⚪",
      PANIC: "🚨", EUPHORIA: "🚀", VOLATILE: "🌊", UNKNOWN: "❓"
    }[result.regime] ?? "❓";

    ctx.log(
      `${symbol} ${emoji} ${result.regime} ` +
      `conf=${result.confidence} ` +
      `[${result.reasons.slice(0, 3).join(" | ")}]`
    );
  }

  if (symbolRegimes.length === 0) {
    ctx.log("⚠️ Aucun régime calculé — features non disponibles sur le bus");
    return;
  }

  // Régime global agrégé
  const { globalRegime, globalConfidence, divergence, votes } =
    aggregateRegimes(symbolRegimes);

  ctx.emit(
    "trading.intel.regime",
    "intel.regime.v1",
    { asset: "MARKET" },
    {
      regime:      globalRegime,
      confidence:  globalConfidence,
      divergence,
      by_symbol:   bySymbol,
      votes,
      ts:          Date.now(),
    }
  );

  const emoji = {
    TREND_UP: "🟢", TREND_DOWN: "🔴", RANGE: "⚪",
    PANIC: "🚨", EUPHORIA: "🚀", VOLATILE: "🌊"
  }[globalRegime] ?? "❓";

  ctx.log(
    `\n🌍 RÉGIME GLOBAL: ${emoji} ${globalRegime} ` +
    `(conf=${globalConfidence}${divergence ? " ⚠️ DIVERGENCE" : ""})`
  );
}
