import { Router } from "express";
import { readFileSync, existsSync, readdirSync, statSync } from "fs";
import { join } from "path";

const router = Router();

// ── Constante racine POLY_FACTORY ─────────────────────────────────────────────
const POLY_BASE_PATH = process.env.POLY_BASE_PATH || "/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state";

// Stratégies connues — fallback si registry vide (paper mode démarrant)
const KNOWN_STRATEGIES = [
  "POLY_ARB_SCANNER", "POLY_WEATHER_ARB",    "POLY_LATENCY_ARB",
  "POLY_BROWNIAN_SNIPER", "POLY_PAIR_COST",  "POLY_OPP_SCORER",
  "POLY_NO_SCANNER", "POLY_CONVERGENCE_STRAT", "POLY_NEWS_STRAT",
];

const INITIAL_CAPITAL = 1000.0; // 1 000€ par stratégie
const POSITIONS_LIMIT_PER_STRATEGY = 6;

// ── Cache TTLs ────────────────────────────────────────────────────────────────
const LIVE_TTL       = 30_000;  // /live       → 30s
const STRATEGIES_TTL = 60_000;  // /strategies → 60s
const TRADES_TTL     = 60_000;  // /trades     → 60s (données brutes)
const HEALTH_TTL     = 30_000;  // /health     → 30s

let liveCache       = null; let liveCacheTs       = 0;
let strategiesCache = null; let strategiesCacheTs = 0;
let rawPaperTrades  = null; let rawPaperCacheTs   = 0;
let rawLiveTrades   = null; let rawLiveCacheTs    = 0;
let healthCache     = null; let healthCacheTs     = 0;

// ── Helpers ───────────────────────────────────────────────────────────────────
function readJSON(p) {
  try { return JSON.parse(readFileSync(p, "utf8")); }
  catch { return null; }
}

function readJSONL(p) {
  try {
    return readFileSync(p, "utf8")
      .split("\n").filter(Boolean)
      .map(l => JSON.parse(l));
  } catch { return []; }
}

function fileMtimeSec(p) {
  try { return Math.floor(statSync(p).mtimeMs / 1000); }
  catch { return null; }
}

/** Extrait un ISO timestamp depuis trade_id TRD_YYYYMMDD_XXXX */
function tradeIdToTimestamp(tradeId) {
  if (!tradeId) return null;
  const m = tradeId.match(/^TRD_(\d{4})(\d{2})(\d{2})_/);
  if (!m) return null;
  return `${m[1]}-${m[2]}-${m[3]}T00:00:00Z`;
}

/** Calcule win_rate, sharpe, max_drawdown depuis des trades avec pnl_eur */
function computeMetrics(trades) {
  const closed = trades.filter(t => t.pnl_eur != null);
  if (closed.length < 2) return { win_rate: null, sharpe: null, max_drawdown: 0 };

  const wins     = closed.filter(t => t.pnl_eur > 0).length;
  const win_rate = parseFloat((wins / closed.length * 100).toFixed(1));

  const returns  = closed.map(t => t.pnl_eur);
  const mean     = returns.reduce((s, r) => s + r, 0) / returns.length;
  const variance = returns.reduce((s, r) => s + (r - mean) ** 2, 0) / returns.length;
  const std      = Math.sqrt(variance);
  const sharpe   = std > 0 ? parseFloat((mean / std).toFixed(2)) : null;

  let peak = 0, maxDd = 0, cum = 0;
  for (const t of closed) {
    cum += t.pnl_eur;
    if (cum > peak) peak = cum;
    const dd = peak > 0 ? (peak - cum) / peak : 0;
    if (dd > maxDd) maxDd = dd;
  }

  return { win_rate, sharpe, max_drawdown: parseFloat((maxDd * 100).toFixed(2)) };
}

/** Charge tous les fichiers ACC_POLY_*.json → map stratégie → données compte */
function loadAccounts() {
  const accountsDir = join(POLY_BASE_PATH, "accounts");
  const result = {};
  if (!existsSync(accountsDir)) return result;
  try {
    readdirSync(accountsDir)
      .filter(f => f.startsWith("ACC_") && f.endsWith(".json"))
      .forEach(f => {
        const data = readJSON(join(accountsDir, f));
        if (data?.strategy) result[data.strategy] = data;
      });
  } catch {}
  return result;
}

/** Charge les positions ouvertes.
 *  Source primaire : portfolio_state.json (écrit par PolyRiskGuardian.add_position).
 *  Fallback temporaire : paper_trades_log.jsonl — regroupe les trades par
 *  (strategy, market_id) pour reconstituer les positions ouvertes.
 *  Ce fallback existe car les trades antérieurs au 2026-03-18 ont été exécutés
 *  avant le câblage de add_position(). Il deviendra inactif dès que
 *  portfolio_state.json sera créé par le prochain trade. */
function loadOpenPositions() {
  const primary = readJSON(join(POLY_BASE_PATH, "risk", "portfolio_state.json"));
  if (primary?.open_positions) return primary.open_positions;

  // Fallback temporaire : reconstituer depuis paper_trades_log.jsonl
  const trades = readJSONL(join(POLY_BASE_PATH, "trading", "paper_trades_log.jsonl"));
  if (!trades.length) return [];
  const grouped = {};
  for (const t of trades) {
    const key = `${t.strategy ?? "unknown"}::${t.market_id ?? "unknown"}`;
    if (!grouped[key]) {
      grouped[key] = {
        strategy:  t.strategy  ?? null,
        market_id: t.market_id ?? null,
        size_eur:  0,
        category:  t.category  ?? null,
        opened_at: null,
      };
    }
    grouped[key].size_eur += t.size_eur ?? 0;
    // Keep earliest trade timestamp as opened_at
    const ts = tradeIdToTimestamp(t.trade_id);
    if (!grouped[key].opened_at || (ts && ts < grouped[key].opened_at)) {
      grouped[key].opened_at = ts;
    }
  }
  return Object.values(grouped);
}

/** Charge les trades depuis le JSONL paper ou live (avec cache TTL) */
function getCachedTrades(mode) {
  const now = Date.now();
  if (mode === "live") {
    if (rawLiveTrades && now - rawLiveCacheTs < TRADES_TTL) return rawLiveTrades;
    const filename = join(POLY_BASE_PATH, "trading", "live_trades_log.jsonl");
    rawLiveTrades  = readJSONL(filename).map(t => ({ ...t, mode: "live" }));
    rawLiveCacheTs = now;
    return rawLiveTrades;
  }
  if (rawPaperTrades && now - rawPaperCacheTs < TRADES_TTL) return rawPaperTrades;
  const filename = join(POLY_BASE_PATH, "trading", "paper_trades_log.jsonl");
  rawPaperTrades  = readJSONL(filename).map(t => ({ ...t, mode: "paper" }));
  rawPaperCacheTs = now;
  return rawPaperTrades;
}

// ── GET /live ─────────────────────────────────────────────────────────────────
router.get("/live", (req, res) => {
  const now = Date.now();
  if (liveCache && now - liveCacheTs < LIVE_TTL) return res.json(liveCache);

  const heartbeat      = readJSON(join(POLY_BASE_PATH, "orchestrator", "heartbeat_state.json"));
  const accounts       = loadAccounts();
  const openPositions  = loadOpenPositions();
  const paperTrades    = getCachedTrades("paper");
  const liveTrades     = getCachedTrades("live");
  const allTrades      = [...paperTrades, ...liveTrades];

  const strategyNames = Object.keys(accounts).length > 0
    ? Object.keys(accounts)
    : KNOWN_STRATEGIES;

  // Positions par stratégie (must be computed before strategy loop)
  const positionsByStrategy = {};
  let total_capital_committed = 0;
  for (const pos of openPositions) {
    const sn = pos.strategy ?? "unknown";
    if (!positionsByStrategy[sn]) positionsByStrategy[sn] = { count: 0, committed: 0 };
    positionsByStrategy[sn].count += 1;
    positionsByStrategy[sn].committed += pos.size_eur ?? 0;
    total_capital_committed += pos.size_eur ?? 0;
  }

  let total_capital_deployed  = 0;
  let total_capital_available = 0;
  let total_pnl_paper        = 0;
  let pnl_today              = 0;
  const active_strategies    = [];

  // P&L réalisé = uniquement trades sur marchés RÉSOLUS.
  // acc.pnl.total dans les account files inclut le coût des positions ouvertes
  // comme si c'était une perte — ce n'est PAS un P&L réalisé.
  // On calcule le P&L réalisé depuis les trades clôturés uniquement.
  const closedTrades = allTrades.filter(t => t.pnl_eur != null);
  const realizedPnlByStrategy = {};
  for (const t of closedTrades) {
    const sn = t.strategy ?? "unknown";
    realizedPnlByStrategy[sn] = (realizedPnlByStrategy[sn] ?? 0) + (t.pnl_eur ?? 0);
  }

  for (const name of strategyNames) {
    const acc     = accounts[name];
    const initial = acc?.capital?.initial   ?? INITIAL_CAPITAL;
    const stPos   = positionsByStrategy[name] ?? { count: 0, committed: 0 };
    const committed = stPos.committed;
    // Capital disponible = initial - engagé dans positions ouvertes
    const avail   = parseFloat((initial - committed).toFixed(2));
    // P&L réalisé = uniquement trades résolus (pnl_eur non null dans le ledger)
    const realizedPnl = realizedPnlByStrategy[name] ?? 0;
    const dayPnl  = acc?.pnl?.daily        ?? 0;
    total_capital_deployed  += initial;
    total_capital_available += avail;
    total_pnl_paper        += realizedPnl;
    pnl_today              += dayPnl;
    active_strategies.push({
      name,
      status:              acc?.status ?? "paper_testing",
      capital:             parseFloat(initial.toFixed(2)),
      capital_initial:     parseFloat(initial.toFixed(2)),
      capital_available:   parseFloat(avail.toFixed(2)),
      capital_committed:   parseFloat(committed.toFixed(2)),
      capital_engaged_pct: initial > 0 ? parseFloat((committed / initial * 100).toFixed(2)) : null,
      pnl_eur:             parseFloat(realizedPnl.toFixed(2)),
      pnl_daily:           parseFloat(dayPnl.toFixed(2)),
      roi_pct:             initial > 0 ? parseFloat((realizedPnl / initial * 100).toFixed(2)) : null,
      positions_open:      stPos.count,
      positions_limit:     POSITIONS_LIMIT_PER_STRATEGY,
    });
  }

  const global_status = readJSON(join(POLY_BASE_PATH, "risk", "global_risk_state.json"))?.status ?? "NORMAL";

  // Métriques globales calculées sur les trades avec P&L connu
  const { sharpe: sharpe_global, max_drawdown: max_drawdown_global } =
    computeMetrics(allTrades);

  // Score santé (0–100) basé sur les state files lisibles
  let system_health_score = 100;
  if (global_status === "ARRET_TOTAL")   system_health_score -= 40;
  else if (global_status === "CRITIQUE") system_health_score -= 20;
  else if (global_status === "ALERTE")   system_health_score -= 10;
  const deadLetterCount = readJSONL(join(POLY_BASE_PATH, "bus", "dead_letter.jsonl")).length;
  if (deadLetterCount > 0) system_health_score -= Math.min(deadLetterCount * 5, 20);
  if (heartbeat?.agents) {
    const disabled = Object.values(heartbeat.agents).filter(a => a.status === "disabled").length;
    system_health_score -= disabled * 15;
  }
  system_health_score = Math.max(0, system_health_score);

  const recent_trades = allTrades.slice(-10).reverse().map(t => ({
    trade_id:  t.trade_id,
    mode:      t.mode,
    strategy:  t.strategy  ?? null,
    market_id: t.market_id ?? null,
    direction: t.direction ?? null,
    fill_price: t.fill_price ?? null,
    size_eur:  t.size_eur  ?? null,
    fees:      t.fees      ?? null,
    timestamp: tradeIdToTimestamp(t.trade_id),
  }));

  liveCache = {
    ts:                     now,
    global_status,
    kill_switch_status:     global_status,
    total_capital_deployed:  parseFloat(total_capital_deployed.toFixed(2)),
    total_capital_available: parseFloat(total_capital_available.toFixed(2)),
    total_capital_committed: parseFloat(total_capital_committed.toFixed(2)),
    total_pnl_paper:        parseFloat(total_pnl_paper.toFixed(2)),
    pnl_today:              parseFloat(pnl_today.toFixed(2)),
    unrealized_pnl:         null,  // Not calculable without mark-price resolution
    open_positions_count:   openPositions.length,
    open_positions:         openPositions.map(p => ({
      strategy:   p.strategy   ?? null,
      market_id:  p.market_id  ?? null,
      size_eur:   p.size_eur   ?? null,
      category:   p.category   ?? null,
      direction:  p.direction  ?? null,
      opened_at:  p.opened_at  ?? null,
      market_url: p.market_id  ? `https://polymarket.com/markets?id=${p.market_id}` : null,
    })),
    active_strategies_count: active_strategies.filter(s => s.status !== "stopped").length,
    sharpe_global,
    max_drawdown_global,
    system_health_score,
    active_strategies,
    recent_trades,
  };
  liveCacheTs = now;
  res.json(liveCache);
});

// ── GET /strategies ───────────────────────────────────────────────────────────
router.get("/strategies", (req, res) => {
  const now = Date.now();
  if (strategiesCache && now - strategiesCacheTs < STRATEGIES_TTL) return res.json(strategiesCache);

  const registry       = readJSON(join(POLY_BASE_PATH, "registry", "strategy_registry.json"));
  const accounts       = loadAccounts();
  const openPositions  = loadOpenPositions();
  const paperTrades    = getCachedTrades("paper");
  const liveTrades     = getCachedTrades("live");
  const allTrades      = [...paperTrades, ...liveTrades];

  // Positions par stratégie (from portfolio_state.json)
  const stratPosCounts = {};
  const stratPosCommit = {};
  for (const pos of openPositions) {
    const sn = pos.strategy ?? "unknown";
    stratPosCounts[sn] = (stratPosCounts[sn] ?? 0) + 1;
    stratPosCommit[sn] = (stratPosCommit[sn] ?? 0) + (pos.size_eur ?? 0);
  }

  // Index des trades par stratégie
  const tradesByStrategy = {};
  for (const t of allTrades) {
    if (!t.strategy) continue;
    if (!tradesByStrategy[t.strategy]) tradesByStrategy[t.strategy] = [];
    tradesByStrategy[t.strategy].push(t);
  }

  const registryStrategies = registry?.strategies ?? {};
  const strategyNames = Object.keys(registryStrategies).length > 0
    ? Object.keys(registryStrategies)
    : KNOWN_STRATEGIES;

  // P&L réalisé par stratégie (uniquement trades résolus)
  const realizedByStrat = {};
  for (const t of allTrades.filter(t => t.pnl_eur != null)) {
    const sn = t.strategy ?? "unknown";
    realizedByStrat[sn] = (realizedByStrat[sn] ?? 0) + (t.pnl_eur ?? 0);
  }

  const strategies = strategyNames.map(name => {
    const acc     = accounts[name];
    const regData = registryStrategies[name] ?? {};
    const trades  = tradesByStrategy[name]   ?? [];
    const { win_rate, sharpe, max_drawdown } = computeMetrics(trades);

    const initial     = acc?.capital?.initial   ?? INITIAL_CAPITAL;
    const nPos        = stratPosCounts[name] ?? 0;
    const committed   = stratPosCommit[name] ?? 0;
    const avail       = parseFloat((initial - committed).toFixed(2));
    const realizedPnl = realizedByStrat[name] ?? 0;
    const pnl_daily   = acc?.pnl?.daily        ?? 0;
    const pnl_percent = parseFloat(((realizedPnl / initial) * 100).toFixed(2));
    const drawdown    = acc?.drawdown?.max_drawdown_pct ?? max_drawdown ?? 0;

    const lastTrade   = trades.length ? trades[trades.length - 1] : null;

    return {
      name,
      mode:                regData.status?.includes("live") ? "live" : "paper",
      status:              acc?.status          ?? regData.status ?? "paper_testing",
      capital:             parseFloat(initial.toFixed(2)),
      capital_initial:     parseFloat(initial.toFixed(2)),
      capital_available:   parseFloat(avail.toFixed(2)),
      capital_committed:   parseFloat(committed.toFixed(2)),
      capital_engaged_pct: initial > 0 ? parseFloat((committed / initial * 100).toFixed(2)) : null,
      pnl_eur:             parseFloat(realizedPnl.toFixed(2)),
      pnl_daily:           parseFloat(pnl_daily.toFixed(2)),
      pnl_percent,
      roi_pct:             initial > 0 ? parseFloat((realizedPnl / initial * 100).toFixed(2)) : null,
      unrealized_pnl:      null,
      win_rate,
      sharpe,
      drawdown:            parseFloat(drawdown.toFixed(2)),
      trades_total:        acc?.performance?.total_trades ?? trades.length,
      positions_open:      nPos,
      positions_limit:     POSITIONS_LIMIT_PER_STRATEGY,
      last_activity:       lastTrade ? tradeIdToTimestamp(lastTrade.trade_id) : null,
      promotion_status:    regData.promotion_requested ? "pending" : null,
    };
  });

  strategiesCache = { ts: now, count: strategies.length, strategies };
  strategiesCacheTs = now;
  res.json(strategiesCache);
});

// ── GET /trades ───────────────────────────────────────────────────────────────
// Params : ?mode=paper|live  &strategy=POLY_ARB_SCANNER  &limit=50  &offset=0
router.get("/trades", (req, res) => {
  const { mode, strategy, limit = "50", offset = "0" } = req.query;
  const lim = Math.min(parseInt(limit,  10) || 50, 200);
  const off = parseInt(offset, 10) || 0;

  // Lecture depuis les caches TTL (données brutes, non filtrées)
  let trades = [];
  if (!mode || mode === "paper") trades.push(...getCachedTrades("paper"));
  if (!mode || mode === "live")  trades.push(...getCachedTrades("live"));

  if (strategy) trades = trades.filter(t => t.strategy === strategy);

  const total = trades.length;
  const page  = trades.slice(off, off + lim).map(t => ({
    trade_id:   t.trade_id    ?? null,
    mode:       t.mode,
    strategy:   t.strategy    ?? null,
    market_id:  t.market_id   ?? null,
    direction:  t.direction   ?? null,
    fill_price: t.fill_price  ?? null,
    size_eur:   t.size_eur    ?? null,
    fees:       t.fees        ?? null,
    slippage:   t.slippage_actual ?? null,
    pnl_eur:    null,   // Non disponible avant résolution du marché
    duration_ms: null,  // Non applicable (marché de prédiction binaire)
    timestamp:  tradeIdToTimestamp(t.trade_id),
  }));

  res.json({ ts: Date.now(), total, count: page.length, offset: off, limit: lim, trades: page });
});

// ── GET /health ───────────────────────────────────────────────────────────────
router.get("/health", (req, res) => {
  const now = Date.now();
  if (healthCache && now - healthCacheTs < HEALTH_TTL) return res.json(healthCache);

  const sysState    = readJSON(join(POLY_BASE_PATH, "orchestrator", "system_state.json"))    ?? {};
  const heartbeat   = readJSON(join(POLY_BASE_PATH, "orchestrator", "heartbeat_state.json")) ?? {};
  // pending_events.jsonl is a cumulative event log, not a queue — count lines without loading
  let busEventsTotal = 0;
  try {
    const content = readFileSync(join(POLY_BASE_PATH, "bus", "pending_events.jsonl"), "utf8");
    busEventsTotal = content.split("\n").filter(Boolean).length;
  } catch {}
  let processedTotal = 0;
  try {
    const content = readFileSync(join(POLY_BASE_PATH, "bus", "processed_events.jsonl"), "utf8");
    processedTotal = content.split("\n").filter(Boolean).length;
  } catch {}
  const deadLetters = readJSONL(join(POLY_BASE_PATH, "bus", "dead_letter.jsonl"));

  const agents_status = Object.entries(heartbeat.agents ?? {}).map(([name, d]) => ({
    name,
    status:          d.status          ?? "unknown",
    last_seen:       d.last_seen        ?? null,
    expected_freq_s: d.expected_freq_s  ?? null,
    restart_count:   d.restart_count    ?? 0,
  }));

  // Fraîcheur des flux (epoch secondes de la dernière écriture du fichier)
  const signal_freshness = {
    binance_last_update_s: fileMtimeSec(join(POLY_BASE_PATH, "feeds", "binance_raw.json")),
    noaa_last_update_s:    fileMtimeSec(join(POLY_BASE_PATH, "feeds", "noaa_forecasts.json")),
    wallets_last_update_s: fileMtimeSec(join(POLY_BASE_PATH, "feeds", "wallet_raw_positions.json")),
    market_last_update_s:  fileMtimeSec(join(POLY_BASE_PATH, "feeds", "polymarket_prices.json")),
  };

  healthCache = {
    ts:                     now,
    orchestrator_last_cycle: sysState.last_nightly_run ?? null,
    bus_events_total:       busEventsTotal,
    bus_processed_total:    processedTotal,
    bus_pending_real:       Math.max(0, busEventsTotal - processedTotal),
    dead_letter_count:      deadLetters.length,
    agents_status,
    signal_freshness,
  };
  healthCacheTs = now;
  res.json(healthCache);
});

export default router;
