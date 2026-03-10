import { Router } from "express";
import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const router = Router();
const STATE_DIR  = process.env.STATE_DIR;
const AGGREGATES = process.env.AGGREGATES_DIR;

// Caches
let liveCache = null;    let liveCacheTs = 0;
let historyCache = null; let historyCacheTs = 0;
const LIVE_TTL    = 30_000;
const HISTORY_TTL = 10 * 60_000;

function readJSON(path) {
  try { return JSON.parse(readFileSync(path, "utf8")); }
  catch { return null; }
}

function readJSONL(path) {
  try {
    return readFileSync(path, "utf8")
      .split("\n").filter(Boolean)
      .map(l => JSON.parse(l));
  } catch { return []; }
}

// Live — état temps réel du pipeline trading
router.get("/live", (req, res) => {
  const now = Date.now();
  if (liveCache && now - liveCacheTs < LIVE_TTL)
    return res.json(liveCache);

  // Lire les états des agents clés
  const agents = [
    "KILL_SWITCH_GUARDIAN", "POLICY_ENGINE", "TRADE_GENERATOR",
    "RISK_MANAGER", "TRADING_ORCHESTRATOR", "TESTNET_EXECUTOR",
    "REGIME_DETECTOR", "PREDICTOR", "PERFORMANCE_ANALYST",
    "STRATEGY_GATEKEEPER"
  ];

  const agentStates = {};
  for (const id of agents) {
    const s = readJSON(`${STATE_DIR}/memory/${id}.state.json`);
    if (s) agentStates[id] = {
      last_run_ts: s.stats?.last_run_ts ?? null,
      runs:        s.stats?.runs        ?? 0,
      errors:      s.stats?.errors      ?? 0,
    };
  }

  // Kill switch
  const ks = readJSON(`${STATE_DIR}/memory/KILL_SWITCH_GUARDIAN.state.json`);
  const killSwitchArmed = ks?.kill_switch_armed ?? false;

  // Positions ouvertes
  const ledger = readJSON(`${STATE_DIR}/ledger/positions.json`);
  const openPositions = ledger?.open ?? [];

  // Dernier trade
  const trades = readJSONL(`${STATE_DIR}/ledger/trades.jsonl`);
  const lastTrade = trades.length ? trades[trades.length - 1] : null;

  // PnL du jour
  const today = new Date().toISOString().slice(0, 10);
  const todayTrades = trades.filter(t => t.closed_at?.startsWith(today));
  const pnlToday = todayTrades.reduce((s, t) => s + (t.pnl_usd ?? 0), 0);

  // Régime actuel
  const regime = readJSON(`${STATE_DIR}/memory/REGIME_DETECTOR.state.json`);

  liveCache = {
    ts: now,
    kill_switch_armed: killSwitchArmed,
    regime: regime?.last_regime ?? null,
    open_positions: openPositions.length,
    positions: openPositions.slice(0, 5),
    last_trade: lastTrade,
    pnl_today: parseFloat(pnlToday.toFixed(4)),
    trades_today: todayTrades.length,
    agents: agentStates,
  };
  liveCacheTs = now;
  res.json(liveCache);
});

// History — courbe PnL 30 jours
router.get("/history", (req, res) => {
  const now = Date.now();
  if (historyCache && now - historyCacheTs < HISTORY_TTL)
    return res.json(historyCache);

  const agg = readJSON(`${AGGREGATES}/trading_daily.json`);
  if (agg) {
    historyCache = { ts: now, ...agg };
    historyCacheTs = now;
    return res.json(historyCache);
  }

  // Fallback lecture directe
  const trades = readJSONL(`${STATE_DIR}/ledger/trades.jsonl`);
  const byDate = {};
  for (const t of trades) {
    const d = t.closed_at?.slice(0, 10);
    if (!d) continue;
    if (!byDate[d]) byDate[d] = { pnl: 0, trades: 0, wins: 0 };
    byDate[d].pnl    += t.pnl_usd ?? 0;
    byDate[d].trades += 1;
    if ((t.pnl_usd ?? 0) > 0) byDate[d].wins += 1;
  }

  const history = Object.entries(byDate)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-30)
    .map(([date, d]) => ({
      date,
      pnl:      parseFloat(d.pnl.toFixed(4)),
      trades:   d.trades,
      win_rate: d.trades ? parseFloat((d.wins / d.trades * 100).toFixed(1)) : 0,
    }));

  const totalPnl   = history.reduce((s, d) => s + d.pnl, 0);
  const totalTrades = history.reduce((s, d) => s + d.trades, 0);

  historyCache = { ts: now, history, total_pnl: parseFloat(totalPnl.toFixed(4)), total_trades: totalTrades };
  historyCacheTs = now;
  res.json(historyCache);
});

export default router;
