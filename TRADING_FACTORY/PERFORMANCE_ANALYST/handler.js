/**
 * PERFORMANCE_ANALYST — Handler
 * Lit trading.exec.trade.ledger et calcule les métriques par :
 *   - stratégie
 *   - asset
 *   - régime de marché
 * Met à jour :
 *   - state/trading/learning/strategy_performance.json
 *   - state/trading/learning/asset_performance.json
 *   - state/trading/learning/regime_performance_matrix.json
 *   - state/trading/learning/daily_performance.json
 * Pas de LLM — calcul pur.
 */

import fs   from "fs";
import path from "path";

let loadRegistry, loadWallet;
try {
  const su = await import("../_shared/strategy_utils.js");
  loadRegistry = su.loadRegistry;
  loadWallet   = su.loadWallet;
} catch { /* fallback: registry not available */ }

function readJSON(p, def) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); } catch { return def; }
}

function writeJSON(p, d) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(d, null, 2));
}

// ─── Calcul métriques sur un ensemble de trades ──────────────────────────

function calcMetrics(trades, capitalUSD = 10000) {
  if (!trades.length) return null;

  const wins   = trades.filter(t => (t.pnl_usd ?? 0) >= 0);
  const losses = trades.filter(t => (t.pnl_usd ?? 0) < 0);
  const pnl    = trades.reduce((s, t) => s + (t.pnl_usd ?? 0), 0);

  const totalWins   = wins.reduce((s, t) => s + (t.pnl_usd ?? 0), 0);
  const totalLosses = Math.abs(losses.reduce((s, t) => s + (t.pnl_usd ?? 0), 0));
  const avgWin      = wins.length   ? totalWins   / wins.length   : 0;
  const avgLoss     = losses.length ? totalLosses / losses.length : 0;
  const winRate     = trades.length ? wins.length / trades.length : 0;
  const profitFactor = totalLosses > 0 ? totalWins / totalLosses : totalWins > 0 ? 99 : 0;
  const expectancy   = (winRate * avgWin) - ((1 - winRate) * avgLoss);

  // Drawdown max
  let peak = 0, maxDd = 0, cumPnl = 0;
  for (const t of trades.sort((a, b) => (a.closed_at ?? 0) - (b.closed_at ?? 0))) {
    cumPnl += (t.pnl_usd ?? 0);
    if (cumPnl > peak) peak = cumPnl;
    const dd = peak > 0 ? (peak - cumPnl) / peak : 0;
    if (dd > maxDd) maxDd = dd;
  }

  // Sharpe simplifié (sans taux sans risque)
  const returns = trades.map(t => (t.pnl_usd ?? 0) / capitalUSD);
  const mean    = returns.reduce((s, r) => s + r, 0) / returns.length;
  const variance = returns.reduce((s, r) => s + Math.pow(r - mean, 2), 0) / returns.length;
  const sharpe  = variance > 0 ? mean / Math.sqrt(variance) : 0;

  const avgHold = trades.reduce((s, t) => s + (t.hold_ms ?? 0), 0) / trades.length;

  return {
    trades_count:      trades.length,
    win_count:         wins.length,
    loss_count:        losses.length,
    wins:              wins.length,
    losses:            losses.length,
    win_rate:          parseFloat((winRate * 100).toFixed(2)),
    win_rate_pct:      trades.length > 0 ? parseFloat((winRate * 100).toFixed(2)) : null,
    pnl_usd:           parseFloat(pnl.toFixed(2)),
    realized_pnl_usd:  parseFloat(pnl.toFixed(2)),
    roi_pct:           parseFloat((pnl / capitalUSD * 100).toFixed(4)),
    gross_wins_usd:    parseFloat(totalWins.toFixed(2)),
    gross_losses_usd:  parseFloat(totalLosses.toFixed(2)),
    avg_win_usd:       parseFloat(avgWin.toFixed(2)),
    avg_loss_usd:      parseFloat(avgLoss.toFixed(2)),
    profit_factor:     totalLosses > 0 ? parseFloat((totalWins / totalLosses).toFixed(3)) : (totalWins > 0 ? null : null),
    expectancy_usd:    parseFloat(expectancy.toFixed(2)),
    max_drawdown_pct:  parseFloat((maxDd * 100).toFixed(2)),
    sharpe_ratio:      parseFloat(sharpe.toFixed(3)),
    avg_hold_min:      parseFloat((avgHold / 60000).toFixed(1)),
    last_updated:      new Date().toISOString(),
  };
}

// ─── Rolling ROI ────────────────────────────────────────────────────────────

function calcRollingROI(trades, days, capitalUSD) {
  const cutoff = Date.now() - days * 24 * 3600 * 1000;
  const recent = trades.filter(t => (t.closed_at ?? 0) >= cutoff);
  if (recent.length === 0) return null;
  const pnl = recent.reduce((s, t) => s + (t.pnl_usd ?? 0), 0);
  return parseFloat((pnl / capitalUSD * 100).toFixed(4));
}

// ─── Strategy Ranking ───────────────────────────────────────────────────────

const RANKING_MIN_TRADES = 10;
const RANKING_WARMUP     = 1;

const WEIGHTS = {
  roi_pct:           0.30,
  max_drawdown_pct:  0.20,  // inversé
  profit_factor:     0.20,
  win_rate_pct:      0.10,
  trade_count:       0.10,
  roi_14d_pct:       0.10,
};

function normalize(values) {
  if (values.length <= 1) return values.map(() => 1);
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max === min) return values.map(() => 1);
  return values.map(v => (v - min) / (max - min));
}

function buildStrategyRanking(ctx, byStrategy, registry, learnDir) {
  const now = new Date().toISOString();
  const allStrategyIds = registry ? Object.keys(registry).filter(k => registry[k].enabled) : Object.keys(byStrategy);

  const strategies = {};
  const rankedEntries = [];

  for (const sid of allStrategyIds) {
    const stTrades = byStrategy[sid] ?? [];
    const tradeCount = stTrades.length;

    let capitalForStrat = 1000;
    try {
      if (loadWallet && registry?.[sid]) capitalForStrat = loadWallet(sid).initial_capital;
    } catch {}

    const m = tradeCount > 0 ? calcMetrics(stTrades, capitalForStrat) : null;
    const roi7d  = tradeCount > 0 ? calcRollingROI(stTrades, 7, capitalForStrat) : null;
    const roi14d = tradeCount > 0 ? calcRollingROI(stTrades, 14, capitalForStrat) : null;

    let wallet = null;
    try { if (loadWallet && registry?.[sid]) wallet = loadWallet(sid); } catch {}

    const metrics = {
      roi_pct:           m?.roi_pct ?? 0,
      profit_factor:     m?.profit_factor ?? null,
      win_rate_pct:      m?.win_rate_pct ?? null,
      max_drawdown_pct:  m?.max_drawdown_pct ?? 0,
      roi_7d_pct:        roi7d,
      roi_14d_pct:       roi14d,
      gross_wins_usd:    m?.gross_wins_usd ?? 0,
      gross_losses_usd:  m?.gross_losses_usd ?? 0,
      realized_pnl_usd:  m?.realized_pnl_usd ?? 0,
      equity:            wallet?.equity ?? capitalForStrat,
      initial_capital:   capitalForStrat,
    };

    // Write enriched metrics per strategy
    if (registry?.[sid]) {
      const stratDir = path.join(ctx.stateDir, registry[sid].state_dir);
      if (fs.existsSync(stratDir)) {
        writeJSON(path.join(stratDir, "metrics.json"), {
          strategy_id: sid,
          wallet_id: registry[sid].wallet_id,
          trade_count: tradeCount,
          win_count: m?.win_count ?? 0,
          loss_count: m?.loss_count ?? 0,
          ...metrics,
          last_updated: now,
        });
      }
    }

    let status, message;
    if (tradeCount === 0) {
      status = "insufficient_data";
      message = "Aucun trade fermé — ranking impossible";
    } else if (tradeCount < RANKING_MIN_TRADES) {
      status = "warming_up";
      message = `${tradeCount}/${RANKING_MIN_TRADES} trades — minimum 10 requis pour le ranking`;
    } else {
      status = "ranked";
      message = null;
    }

    const entry = {
      status,
      trade_count: tradeCount,
      message,
      metrics,
      scores: { performance: null, robustness: null, global: null },
    };

    strategies[sid] = entry;

    if (status === "ranked") {
      rankedEntries.push({ strategy_id: sid, metrics, trade_count: tradeCount });
    }
  }

  // ── Compute scores for ranked strategies ──────────────────────────────
  let performanceRanking = [];
  let robustnessRanking  = [];
  let globalRanking      = [];

  if (rankedEntries.length > 0) {
    const rois      = rankedEntries.map(e => e.metrics.roi_pct);
    const dds       = rankedEntries.map(e => e.metrics.max_drawdown_pct);
    const pfs       = rankedEntries.map(e => e.metrics.profit_factor ?? 0);
    const wrs       = rankedEntries.map(e => e.metrics.win_rate_pct ?? 0);
    const tcs       = rankedEntries.map(e => e.trade_count);
    const roi14ds   = rankedEntries.map(e => e.metrics.roi_14d_pct ?? 0);

    const nRoi    = normalize(rois);
    const nDd     = normalize(dds).map(v => 1 - v);  // inversé
    const nPf     = normalize(pfs);
    const nWr     = normalize(wrs);
    const nTc     = normalize(tcs);
    const nRoi14  = normalize(roi14ds);

    for (let i = 0; i < rankedEntries.length; i++) {
      const sid = rankedEntries[i].strategy_id;
      const perfScore = (nRoi[i] * 0.50 + nPf[i] * 0.33 + nWr[i] * 0.17) * 100;
      const robScore  = (nDd[i] * 0.40 + nRoi14[i] * 0.33 + nTc[i] * 0.27) * 100;
      const globalScore =
        nRoi[i]   * WEIGHTS.roi_pct +
        nDd[i]    * WEIGHTS.max_drawdown_pct +
        nPf[i]    * WEIGHTS.profit_factor +
        nWr[i]    * WEIGHTS.win_rate_pct +
        nTc[i]    * WEIGHTS.trade_count +
        nRoi14[i] * WEIGHTS.roi_14d_pct;

      strategies[sid].scores = {
        performance: parseFloat(perfScore.toFixed(1)),
        robustness:  parseFloat(robScore.toFixed(1)),
        global:      parseFloat((globalScore * 100).toFixed(1)),
      };

      const detail = {
        roi_pct:          rankedEntries[i].metrics.roi_pct,
        profit_factor:    rankedEntries[i].metrics.profit_factor,
        win_rate_pct:     rankedEntries[i].metrics.win_rate_pct,
        max_drawdown_pct: rankedEntries[i].metrics.max_drawdown_pct,
        roi_14d_pct:      rankedEntries[i].metrics.roi_14d_pct,
        trade_count:      rankedEntries[i].trade_count,
      };

      performanceRanking.push({ strategy_id: sid, score: strategies[sid].scores.performance, detail });
      robustnessRanking.push({ strategy_id: sid, score: strategies[sid].scores.robustness, detail });
      globalRanking.push({
        strategy_id: sid, status: "ranked",
        score_global: strategies[sid].scores.global,
        score_performance: strategies[sid].scores.performance,
        score_robustness: strategies[sid].scores.robustness,
        detail,
      });
    }

    // Tie-breaker: score → roi_pct → trade_count → strategy_id alphabetical
    const tieSort = (a, b) => {
      const sa = a.score_global ?? a.score ?? 0;
      const sb = b.score_global ?? b.score ?? 0;
      if (sb !== sa) return sb - sa;
      if ((b.detail?.roi_pct ?? 0) !== (a.detail?.roi_pct ?? 0)) return (b.detail?.roi_pct ?? 0) - (a.detail?.roi_pct ?? 0);
      if ((b.detail?.trade_count ?? 0) !== (a.detail?.trade_count ?? 0)) return (b.detail?.trade_count ?? 0) - (a.detail?.trade_count ?? 0);
      return a.strategy_id.localeCompare(b.strategy_id);
    };

    performanceRanking.sort(tieSort);
    robustnessRanking.sort(tieSort);
    globalRanking.sort(tieSort);

    performanceRanking.forEach((e, i) => e.rank = i + 1);
    robustnessRanking.forEach((e, i) => e.rank = i + 1);
    globalRanking.forEach((e, i) => e.rank = i + 1);
  }

  const ranking = {
    generated_at: now,
    ranked_count: rankedEntries.length,
    warming_up_count: Object.values(strategies).filter(s => s.status === "warming_up").length,
    insufficient_data_count: Object.values(strategies).filter(s => s.status === "insufficient_data").length,
    performance_ranking: performanceRanking,
    robustness_ranking:  robustnessRanking,
    global_ranking:      globalRanking,
    strategies,
  };

  writeJSON(path.join(learnDir, "strategy_ranking.json"), ranking);

  ctx.log(`📊 Ranking: ${rankedEntries.length} ranked, ${ranking.warming_up_count} warming_up, ${ranking.insufficient_data_count} insufficient_data`);
  if (globalRanking.length > 0) {
    ctx.log(`   🏆 #1: ${globalRanking[0].strategy_id} (score=${globalRanking[0].score_global})`);
  }
}

// ─── Handler ──────────────────────────────────────────────────────────────

export async function handler(ctx) {
  const learnDir = path.join(ctx.stateDir, "learning");
  fs.mkdirSync(learnDir, { recursive: true });

  // Lire tous les trades du ledger
  const { events } = ctx.bus.readSince("trading.exec.trade.ledger", 0, 10000);
  const trades = events
    .map(e => e.payload)
    .filter(t => t?.status === "closed" && t?.pnl_usd !== undefined);

  // Load registry early for ranking (needed even with 0 trades)
  let registry = null;
  try { if (loadRegistry) registry = loadRegistry(); } catch {}

  if (trades.length === 0) {
    ctx.log("Aucun trade clôturé dans le ledger");
    // Still generate ranking with insufficient_data statuses
    buildStrategyRanking(ctx, {}, registry, learnDir);
    return;
  }

  ctx.log(`📊 Analyse de ${trades.length} trades clôturés`);

  // ── 1. Performance par stratégie ─────────────────────────────────────

  const byStrategy = {};
  for (const t of trades) {
    const k = t.strategy_id ?? t.strategy ?? "unknown";
    if (!byStrategy[k]) byStrategy[k] = [];
    byStrategy[k].push(t);
  }

  const stratPerf = {};
  for (const [strat, stTrades] of Object.entries(byStrategy)) {
    // Use wallet capital if available, else default
    let capitalForStrat = 10000;
    try {
      if (loadWallet && registry?.[strat]) {
        capitalForStrat = loadWallet(strat).initial_capital;
      }
    } catch {}

    const m = calcMetrics(stTrades, capitalForStrat);
    if (m) {
      stratPerf[strat] = { strategy_id: strat, ...m, capital_usd: capitalForStrat };
      ctx.log(
        `  📈 ${strat}: ${m.trades_count} trades | ` +
        `winrate=${m.win_rate}% | PnL=$${m.pnl_usd} | ` +
        `PF=${m.profit_factor} | expectancy=$${m.expectancy_usd}`
      );

      // Write per-strategy metrics file
      if (registry?.[strat]) {
        const stratDir = path.join(ctx.stateDir, registry[strat].state_dir);
        if (fs.existsSync(stratDir)) {
          writeJSON(path.join(stratDir, "metrics.json"), { strategy_id: strat, ...m, capital_usd: capitalForStrat });
        }
      }
    }
  }
  writeJSON(path.join(learnDir, "strategy_performance.json"), stratPerf);

  // ── 2. Performance par asset ──────────────────────────────────────────
  const byAsset = {};
  for (const t of trades) {
    const k = t.symbol ?? "unknown";
    if (!byAsset[k]) byAsset[k] = [];
    byAsset[k].push(t);
  }

  const assetPerf = {};
  for (const [asset, aTrades] of Object.entries(byAsset)) {
    const m     = calcMetrics(aTrades);
    const longs = aTrades.filter(t => t.side === "BUY");
    const shorts = aTrades.filter(t => t.side === "SELL");
    if (m) {
      assetPerf[asset] = {
        asset,
        ...m,
        long_count:  longs.length,
        short_count: shorts.length,
        long_pnl:    parseFloat(longs.reduce((s, t) => s + (t.pnl_usd ?? 0), 0).toFixed(2)),
        short_pnl:   parseFloat(shorts.reduce((s, t) => s + (t.pnl_usd ?? 0), 0).toFixed(2)),
      };
    }
  }
  writeJSON(path.join(learnDir, "asset_performance.json"), assetPerf);

  // ── 3. Matrice régime × stratégie ────────────────────────────────────
  const regimeMatrix = {};
  for (const t of trades) {
    const regime = t.regime ?? "unknown";
    const strat  = t.strategy ?? "unknown";
    const key    = `${regime}__${strat}`;
    if (!regimeMatrix[key]) regimeMatrix[key] = { regime, strategy: strat, trades: [] };
    regimeMatrix[key].trades.push(t);
  }

  const regimePerf = {};
  for (const [key, data] of Object.entries(regimeMatrix)) {
    const m = calcMetrics(data.trades);
    if (m) {
      regimePerf[key] = {
        regime:      data.regime,
        strategy:    data.strategy,
        ...m,
      };
    }
  }
  writeJSON(path.join(learnDir, "regime_performance_matrix.json"), regimePerf);

  // ── 4. Performance journalière ────────────────────────────────────────
  const byDay = {};
  for (const t of trades) {
    const day = new Date(t.closed_at ?? 0).toISOString().slice(0, 10);
    if (!byDay[day]) byDay[day] = [];
    byDay[day].push(t);
  }

  const dailyPerf = {};
  for (const [day, dTrades] of Object.entries(byDay)) {
    const m = calcMetrics(dTrades);
    if (m) dailyPerf[day] = { date: day, ...m };
  }
  writeJSON(path.join(learnDir, "daily_performance.json"), dailyPerf);

  // ── 5. Métriques globales ─────────────────────────────────────────────
  const global = calcMetrics(trades);
  writeJSON(path.join(learnDir, "global_performance.json"), {
    ...global,
    capital_usd:      10000,
    paper_trading:    true,
    first_trade_at:   new Date(Math.min(...trades.map(t => t.closed_at ?? Infinity))).toISOString(),
    last_trade_at:    new Date(Math.max(...trades.map(t => t.closed_at ?? 0))).toISOString(),
  });

  ctx.log(`✅ Métriques mises à jour — ${trades.length} trades analysés`);
  ctx.log(`   Stratégies: ${Object.keys(stratPerf).join(", ")}`);
  ctx.log(`   Assets: ${Object.keys(assetPerf).join(", ")}`);
  ctx.log(`   Global: winrate=${global.win_rate}% PnL=$${global.pnl_usd} PF=${global.profit_factor}`);

  // ── 6. Strategy Ranking ─────────────────────────────────────────────────
  buildStrategyRanking(ctx, byStrategy, registry, learnDir);
}
