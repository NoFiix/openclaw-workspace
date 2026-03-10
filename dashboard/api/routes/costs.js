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

  // Fallback lecture directe JSONL
  const entries = readJSONL(`${STATE_DIR}/learning/token_costs.jsonl`);
  const today   = new Date().toISOString().slice(0, 10);
  const month   = today.slice(0, 7);

  const byAgent = {};
  for (const e of entries) {
    if (!byAgent[e.agent]) byAgent[e.agent] = { today: 0, month: 0, total: 0, model: e.model };
    byAgent[e.agent].total += e.cost_usd;
    if (e.date === today)  byAgent[e.agent].today += e.cost_usd;
    if (e.date?.startsWith(month)) byAgent[e.agent].month += e.cost_usd;
  }

  const totalToday = Object.values(byAgent).reduce((s, a) => s + a.today, 0);
  const totalMonth = Object.values(byAgent).reduce((s, a) => s + a.month, 0);

  summaryCache = { ts: now, today: totalToday, month: totalMonth, by_agent: byAgent };
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
