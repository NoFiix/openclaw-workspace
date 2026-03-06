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
    trades_count:   trades.length,
    wins:           wins.length,
    losses:         losses.length,
    win_rate:       parseFloat((winRate * 100).toFixed(2)),
    pnl_usd:        parseFloat(pnl.toFixed(2)),
    roi_pct:        parseFloat((pnl / capitalUSD * 100).toFixed(4)),
    avg_win_usd:    parseFloat(avgWin.toFixed(2)),
    avg_loss_usd:   parseFloat(avgLoss.toFixed(2)),
    profit_factor:  parseFloat(profitFactor.toFixed(3)),
    expectancy_usd: parseFloat(expectancy.toFixed(2)),
    max_drawdown_pct: parseFloat((maxDd * 100).toFixed(2)),
    sharpe_ratio:   parseFloat(sharpe.toFixed(3)),
    avg_hold_min:   parseFloat((avgHold / 60000).toFixed(1)),
    last_updated:   new Date().toISOString(),
  };
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

  if (trades.length === 0) {
    ctx.log("Aucun trade clôturé dans le ledger");
    return;
  }

  ctx.log(`📊 Analyse de ${trades.length} trades clôturés`);

  // ── 1. Performance par stratégie ─────────────────────────────────────
  const byStrategy = {};
  for (const t of trades) {
    const k = t.strategy ?? "unknown";
    if (!byStrategy[k]) byStrategy[k] = [];
    byStrategy[k].push(t);
  }

  const stratPerf = {};
  for (const [strat, stTrades] of Object.entries(byStrategy)) {
    const m = calcMetrics(stTrades);
    if (m) {
      stratPerf[strat] = { strategy_id: strat, ...m };
      ctx.log(
        `  📈 ${strat}: ${m.trades_count} trades | ` +
        `winrate=${m.win_rate}% | PnL=$${m.pnl_usd} | ` +
        `PF=${m.profit_factor} | expectancy=$${m.expectancy_usd}`
      );
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
}
