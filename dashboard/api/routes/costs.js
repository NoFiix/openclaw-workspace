import { Router } from "express";
import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const router = Router();
const STATE_DIR  = process.env.STATE_DIR;
const AGGREGATES = process.env.AGGREGATES_DIR;

// Cache 5min pour summary, 15min pour history
let summaryCache = null; let summaryCacheTs = 0;
let historyCache = null; let historyCacheTs = 0;
const SUMMARY_TTL = 5 * 60_000;
const HISTORY_TTL = 15 * 60_000;

function readJSONL(path) {
  try {
    return readFileSync(path, "utf8")
      .split("\n").filter(Boolean)
      .map(l => JSON.parse(l));
  } catch { return []; }
}

function readJSON(path) {
  try { return JSON.parse(readFileSync(path, "utf8")); }
  catch { return null; }
}

// Summary — coûts du jour + du mois par agent
router.get("/summary", (req, res) => {
  const now = Date.now();
  if (summaryCache && now - summaryCacheTs < SUMMARY_TTL)
    return res.json(summaryCache);

  // Lire depuis agrégat si dispo, sinon recalculer depuis JSONL
  const agg = readJSON(`${AGGREGATES}/llm_daily.json`);
  if (agg) {
    summaryCache = agg;
    summaryCacheTs = now;
    return res.json(agg);
  }

  // Fallback lecture directe JSONL — merge Trading + POLY_FACTORY costs
  const tradingEntries = readJSONL(`${STATE_DIR}/learning/token_costs.jsonl`);
  const polyPath = process.env.POLY_BASE_PATH ?? "/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state";
  const polyEntries = readJSONL(`${polyPath}/llm/token_costs.jsonl`);
  const entries = [...tradingEntries, ...polyEntries];
  const today   = new Date().toISOString().slice(0, 10);
  const month   = today.slice(0, 7);
  const weekAgo = new Date(now - 7 * 86400000).toISOString().slice(0, 10);

  const init = () => ({
    today:  { calls: 0, input_tokens: 0, output_tokens: 0, cost: 0 },
    week:   { calls: 0, input_tokens: 0, output_tokens: 0, cost: 0 },
    month:  { calls: 0, input_tokens: 0, output_tokens: 0, cost: 0 },
    total:  0,
    model:  null,
  });

  const byAgent = {};
  for (const e of entries) {
    if (!byAgent[e.agent]) byAgent[e.agent] = init();
    const a = byAgent[e.agent];
    a.model = e.model ?? a.model;
    a.total += e.cost_usd ?? 0;
    const inp = e.input ?? 0;
    const out = e.output ?? 0;
    const cost = e.cost_usd ?? 0;
    if (e.date === today) {
      a.today.calls++; a.today.input_tokens += inp; a.today.output_tokens += out; a.today.cost += cost;
    }
    if (e.date >= weekAgo) {
      a.week.calls++; a.week.input_tokens += inp; a.week.output_tokens += out; a.week.cost += cost;
    }
    if (e.date?.startsWith(month)) {
      a.month.calls++; a.month.input_tokens += inp; a.month.output_tokens += out; a.month.cost += cost;
    }
  }

  // Round all values
  for (const a of Object.values(byAgent)) {
    for (const period of [a.today, a.week, a.month]) {
      period.cost = parseFloat(period.cost.toFixed(6));
    }
    a.total = parseFloat(a.total.toFixed(6));
  }

  const totalToday = Object.values(byAgent).reduce((s, a) => s + a.today.cost, 0);
  const totalWeek  = Object.values(byAgent).reduce((s, a) => s + a.week.cost, 0);
  const totalMonth = Object.values(byAgent).reduce((s, a) => s + a.month.cost, 0);

  summaryCache = { ts: now, today: totalToday, week: totalWeek, month: totalMonth, by_agent: byAgent };
  summaryCacheTs = now;
  res.json(summaryCache);
});

// History — courbe 30 jours
router.get("/history", (req, res) => {
  const now = Date.now();
  if (historyCache && now - historyCacheTs < HISTORY_TTL)
    return res.json(historyCache);

  const agg = readJSON(`${AGGREGATES}/llm_daily.json`);
  if (agg?.history) {
    historyCache = { ts: now, history: agg.history };
    historyCacheTs = now;
    return res.json(historyCache);
  }

  // Fallback — agréger par date depuis JSONL
  const entries = readJSONL(`${STATE_DIR}/learning/token_costs.jsonl`);
  const byDate  = {};
  for (const e of entries) {
    if (!byDate[e.date]) byDate[e.date] = 0;
    byDate[e.date] += e.cost_usd;
  }

  const history = Object.entries(byDate)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-30)
    .map(([date, cost]) => ({ date, cost: parseFloat(cost.toFixed(6)) }));

  historyCache = { ts: now, history };
  historyCacheTs = now;
  res.json(historyCache);
});

export default router;
