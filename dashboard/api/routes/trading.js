import { Router } from "express";
import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const router = Router();
const STATE_DIR = process.env.STATE_DIR; // e.g. /…/state/trading

// ── Cache TTLs ───────────────────────────────────────────────────────────────
const LIVE_TTL     = 30_000;
const TRADES_TTL   = 60_000;
const PERF_TTL     = 60_000;

let liveCache   = null; let liveCacheTs   = 0;
let tradesCache = null; let tradesCacheTs = 0;
let perfCache   = null; let perfCacheTs   = 0;

// ── Helpers ──────────────────────────────────────────────────────────────────
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

/** Normalize a raw ledger event → trade object (handles both payload/causation formats) */
function normalizeTrade(evt) {
  const payload   = evt?.payload   ?? {};
  const causation = evt?.trace?.causation_id ?? {};
  // The "rich" record is whichever has more fields
  const src = Object.keys(payload).length > 2 ? payload : causation;
  if (!src.symbol && !src.asset) return null; // incomplete record
  return {
    id:          src.id          ?? evt.event_id ?? null,
    symbol:      src.symbol      ?? src.asset    ?? null,
    side:        src.side        ?? null,
    strategy:    src.strategy    ?? null,
    regime:      src.regime      ?? null,
    confidence:  src.confidence  ?? null,
    qty:         src.qty         ?? null,
    entry_price: src.entry_fill  ?? null,
    exit_price:  src.exit_price  ?? null,
    exit_reason: src.exit_reason ?? null,
    stop_loss:   src.stop        ?? null,
    take_profit: src.tp          ?? null,
    pnl_usd:     src.pnl_usd    ?? null,
    pnl_pct:     src.pnl_pct    ?? null,
    hold_ms:     src.hold_ms     ?? null,
    value_usd:   src.value_usd   ?? null,
    env:         src.env         ?? evt.scope?.env ?? "testnet",
    opened_at:   src.opened_at   ?? null,
    closed_at:   src.closed_at   ?? evt.ts ?? null,
    status:      src.status      ?? "closed",
  };
}

// ── /live — état temps réel ──────────────────────────────────────────────────
router.get("/live", (req, res) => {
  const now = Date.now();
  if (liveCache && now - liveCacheTs < LIVE_TTL) return res.json(liveCache);

  // Agents trading — scan dynamique de memory/*.state.json
  const agentStates = {};
  const memoryDir    = join(STATE_DIR, "memory");
  const schedulesDir = join(STATE_DIR, "schedules");

  // Charger schedules pour every_seconds
  const scheduleMap = {};
  if (existsSync(schedulesDir)) {
    try {
      readdirSync(schedulesDir)
        .filter(f => f.endsWith(".schedule.json"))
        .forEach(f => {
          const s = readJSON(join(schedulesDir, f));
          if (s?.agent_id) scheduleMap[s.agent_id] = s.every_seconds ?? null;
        });
    } catch {}
  }

  if (existsSync(memoryDir)) {
    try {
      readdirSync(memoryDir)
        .filter(f => f.endsWith(".state.json"))
        .forEach(f => {
          const id  = f.replace(".state.json", "");
          const s   = readJSON(join(memoryDir, f));
          if (!s) return;
          const lastRun = s.stats?.last_run_ts ?? null;
          const interval = scheduleMap[id] ?? null;
          agentStates[id] = {
            last_run_ts:   lastRun,
            runs:          s.stats?.runs   ?? 0,
            errors:        s.stats?.errors ?? 0,
            every_seconds: interval,
          };
        });
    } catch {}
  }

  // Kill switch — lire exec/killswitch.json
  const ksData          = readJSON(`${STATE_DIR}/exec/killswitch.json`) ?? {};
  const killSwitchArmed = ksData.state === "TRIPPED" || (ksData.state !== "ARMED" && !ksData.state);

  // Positions ouvertes testnet
  const positionsTestnet = readJSON(`${STATE_DIR}/exec/positions_testnet.json`) ?? [];

  // Régime actuel
  const regime = readJSON(`${STATE_DIR}/memory/REGIME_DETECTOR.state.json`);

  // Trades du jour depuis le ledger
  const ledger = readJSONL(`${STATE_DIR}/bus/trading_exec_trade_ledger.jsonl`);
  const trades = ledger.map(normalizeTrade).filter(Boolean);
  const today  = new Date().toISOString().slice(0, 10);
  const todayTrades = trades.filter(t => {
    const ts = typeof t.closed_at === "number" ? t.closed_at : 0;
    return new Date(ts).toISOString().startsWith(today);
  });
  const pnlToday = todayTrades.reduce((s, t) => s + (t.pnl_usd ?? 0), 0);
  const lastTrade = trades.length ? trades[trades.length - 1] : null;

  // Historique PnL 7 jours depuis daily_pnl_testnet.json
  const dailyPnlRaw = readJSON(`${STATE_DIR}/exec/daily_pnl_testnet.json`) ?? {};
  const daily_pnl_history = Object.entries(dailyPnlRaw)
    .map(([date, pnl]) => ({ date: date.slice(5), pnl_usd: pnl }))  // "2026-03-08" → "03-08"
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-7);

  liveCache = {
    ts: now,
    kill_switch_armed: killSwitchArmed,
    kill_switch: { state: ksData.state ?? "ARMED", reason: ksData.reason ?? null, trip_count: ksData.trip_count ?? 0 },
    regime: regime?.last_regime ?? null,
    open_positions: positionsTestnet.length,
    positions: positionsTestnet.slice(0, 10),
    last_trade: lastTrade,
    pnl_today: parseFloat(pnlToday.toFixed(4)),
    trades_today: todayTrades.length,
    daily_pnl_history,
    agents: agentStates,
  };
  liveCacheTs = now;
  res.json(liveCache);
});

// ── /trades — historique complet des trades fermés ───────────────────────────
router.get("/trades", (req, res) => {
  const now = Date.now();
  if (tradesCache && now - tradesCacheTs < TRADES_TTL) return res.json(tradesCache);

  const ledger = readJSONL(`${STATE_DIR}/bus/trading_exec_trade_ledger.jsonl`);
  const trades = ledger.map(normalizeTrade).filter(t => t && t.symbol);

  // PnL cumulé chronologique
  let cumPnl = 0;
  const withCum = trades.map(t => {
    cumPnl += t.pnl_usd ?? 0;
    return { ...t, cum_pnl: parseFloat(cumPnl.toFixed(4)) };
  });

  tradesCache = { ts: now, count: trades.length, trades: withCum };
  tradesCacheTs = now;
  res.json(tradesCache);
});

// ── /performance — global + stratégie + asset ────────────────────────────────
router.get("/performance", (req, res) => {
  const now = Date.now();
  if (perfCache && now - perfCacheTs < PERF_TTL) return res.json(perfCache);

  const global   = readJSON(`${STATE_DIR}/learning/global_performance.json`)   ?? {};
  const strategy = readJSON(`${STATE_DIR}/learning/strategy_performance.json`) ?? {};
  const asset    = readJSON(`${STATE_DIR}/learning/asset_performance.json`)    ?? {};

  perfCache = {
    ts: now,
    global,
    strategy: Object.values(strategy),
    asset:    Object.values(asset),
  };
  perfCacheTs = now;
  res.json(perfCache);
});

// ── /strategies — multi-strategy wallets + ranking ────────────────────────────
let stratCache = null; let stratCacheTs = 0;
router.get("/strategies", (req, res) => {
  const now = Date.now();
  if (stratCache && now - stratCacheTs < PERF_TTL) return res.json(stratCache);

  const registry = readJSON(`${STATE_DIR}/configs/strategies_registry.json`) ?? {};
  const ranking  = readJSON(`${STATE_DIR}/learning/strategy_ranking.json`);

  // Load ALL open positions from all sources
  const posTestnet  = readJSON(`${STATE_DIR}/exec/positions_testnet.json`) ?? [];
  const posPaper    = readJSON(`${STATE_DIR}/exec/positions.json`) ?? [];
  const allPositions = [...posTestnet, ...posPaper];

  // Also load per-strategy position files
  for (const [id, cfg] of Object.entries(registry)) {
    const stratPos = readJSON(join(STATE_DIR, cfg.state_dir ?? `strategies/${id}`, "positions.json")) ?? [];
    for (const p of stratPos) {
      if (p.status === "open" && !allPositions.find(x => x.id === p.id)) {
        allPositions.push(p);
      }
    }
  }

  const strategies = [];

  for (const [id, cfg] of Object.entries(registry)) {
    const wallet  = readJSON(join(STATE_DIR, cfg.state_dir ?? `strategies/${id}`, "wallet.json"));
    const metrics = readJSON(join(STATE_DIR, cfg.state_dir ?? `strategies/${id}`, "metrics.json"));
    const rankData = ranking?.strategies?.[id];

    // Find open positions for this strategy
    const stratPositions = allPositions.filter(p =>
      (p.strategy_id === id || p.strategy === id) && p.status === "open"
    );
    const committed = stratPositions.reduce((sum, p) => sum + (p.value_usd ?? 0), 0);
    const walletCash = wallet?.cash ?? cfg.initial_capital ?? 1000;
    const effectiveCash = parseFloat((walletCash - committed).toFixed(2));

    strategies.push({
      strategy_id:        id,
      strategy_label:     cfg.strategy_label ?? id,
      enabled:            cfg.enabled ?? false,
      lifecycle_status:   cfg.lifecycle_status ?? "unknown",
      execution_target:   cfg.execution_target ?? "paper",
      wallet_mode:        cfg.wallet_mode ?? "virtual",
      initial_capital:    wallet?.initial_capital ?? cfg.initial_capital ?? 1000,
      cash:               walletCash,
      effective_cash:     effectiveCash,
      equity:             wallet?.equity ?? cfg.initial_capital ?? 1000,
      allocated:          wallet?.allocated ?? 0,
      committed:          parseFloat(committed.toFixed(2)),
      open_positions_count: stratPositions.length,
      open_positions:     stratPositions.map(p => ({
        id: p.id, symbol: p.symbol, side: p.side,
        value_usd: p.value_usd, entry_fill: p.entry_fill,
        opened_at: p.opened_at,
      })),
      realized_pnl:     wallet?.realized_pnl ?? 0,
      roi_pct:          wallet?.roi_pct ?? 0,
      max_drawdown:     wallet?.max_drawdown ?? 0,
      trade_count:      wallet?.trade_count ?? metrics?.trade_count ?? 0,
      win_count:        wallet?.win_count ?? metrics?.win_count ?? 0,
      win_rate_pct:     metrics?.win_rate_pct ?? null,
      profit_factor:    metrics?.profit_factor ?? null,
      status:           wallet?.status ?? "unknown",
      ranking_status:   rankData?.status ?? "insufficient_data",
      score_global:     rankData?.scores?.global ?? null,
      updated_at:       wallet?.updated_at ?? null,
    });
  }

  const candidates = readJSON(`${STATE_DIR}/configs/candidates_pending.json`);
  const pendingCount = candidates?.candidates
    ? Object.values(candidates.candidates).filter(c => c.status === "pending_review").length
    : 0;

  stratCache = { ts: now, count: strategies.length, strategies, pending_candidates: pendingCount };
  stratCacheTs = now;
  res.json(stratCache);
});

// ── /history — courbe PnL 30 jours (fallback sur ledger) ────────────────────
router.get("/history", (req, res) => {
  const trades = readJSONL(`${STATE_DIR}/bus/trading_exec_trade_ledger.jsonl`)
    .map(normalizeTrade).filter(Boolean);

  const byDate = {};
  for (const t of trades) {
    const ts = typeof t.closed_at === "number" ? t.closed_at : 0;
    const d  = ts ? new Date(ts).toISOString().slice(0, 10) : null;
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

  const totalPnl    = history.reduce((s, d) => s + d.pnl,    0);
  const totalTrades = history.reduce((s, d) => s + d.trades, 0);
  res.json({ ts: Date.now(), history, total_pnl: parseFloat(totalPnl.toFixed(4)), total_trades: totalTrades });
});

export default router;
