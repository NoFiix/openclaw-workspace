import { Router } from "express";
import { readFileSync, existsSync, statSync, readdirSync } from "fs";
import { join } from "path";

const router = Router();
const WORKSPACE  = process.env.WORKSPACE_DIR  || "/home/openclawadmin/openclaw/workspace";
const AGGREGATES = process.env.AGGREGATES_DIR || "/home/openclawadmin/openclaw/dashboard-data/aggregates";

// Caches
let summaryCache = null; let summaryCacheTs = 0;
let historyCache = null; let historyCacheTs = 0;
const SUMMARY_TTL = 2 * 60_000;
const HISTORY_TTL = 15 * 60_000;

function readJSON(path) {
  try { return JSON.parse(readFileSync(path, "utf8")); }
  catch { return null; }
}

function getLogLastRun(logPath) {
  try {
    const stat = statSync(logPath);
    return stat.mtimeMs;
  } catch { return null; }
}

function countDrafts(draftsPath) {
  try {
    const data = readJSON(draftsPath);
    if (!data) return { total: 0, pending: 0 };
    const all = Object.values(data);
    return {
      total:   all.length,
      pending: all.filter(d => d.status === "pending").length,
      approved: all.filter(d => d.status === "approved").length,
      rejected: all.filter(d => d.status === "rejected").length,
    };
  } catch { return { total: 0, pending: 0 } }
}

// Summary — état temps réel du pipeline content
router.get("/summary", (req, res) => {
  const now = Date.now();
  if (summaryCache && now - summaryCacheTs < SUMMARY_TTL)
    return res.json(summaryCache);

  const agg = readJSON(`${AGGREGATES}/content_daily.json`);

  // Derniers runs scrapers
  const hourlyLastRun = getLogLastRun(`${WORKSPACE}/state/hourly_scraper.log`);
  const dailyLastRun  = getLogLastRun(`${WORKSPACE}/state/daily_scraper.log`);

  // Drafts en attente
  const drafts = countDrafts(`${WORKSPACE}/state/drafts.json`);

  // Agents content factory — CF V2 n'a pas de state.json, utiliser mtime des fichiers memory/
  const CF_AGENTS = {
    performance_analyst: { active: true  },
    news_scoring:        { active: true  },
    copywriter:          { active: false }, // CF V2 dev, non en prod
    publisher:           { active: false },
    builder:             { active: false },
  };
  const agentStates = {};
  for (const [id, meta] of Object.entries(CF_AGENTS)) {
    const memDir = `${WORKSPACE}/agents/${id}/memory`;
    if (!existsSync(memDir)) {
      agentStates[id] = { status: meta.active ? "unknown" : "inactive", last_run_ts: null };
      continue;
    }
    try {
      const files = readdirSync(memDir).filter(f => !f.startsWith("."));
      if (!files.length) {
        agentStates[id] = { status: meta.active ? "unknown" : "inactive", last_run_ts: null };
        continue;
      }
      const lastMtimeMs = Math.max(...files.map(f => {
        try { return statSync(join(memDir, f)).mtimeMs; } catch { return 0; }
      }));
      agentStates[id] = {
        status:      !meta.active ? "inactive" : lastMtimeMs && (Date.now() - lastMtimeMs) < 7 * 86400 * 1000 ? "ok" : "warn",
        last_run_ts: lastMtimeMs || null,  // ms — cohérent avec timeAgo() du frontend
      };
    } catch {
      agentStates[id] = { status: "unknown", last_run_ts: null };
    }
  }

  // Historique publications — content_publish_history.json (écrit par poller.js)
  const histPath = `${WORKSPACE}/state/content_publish_history.json`;
  const hist = readJSON(histPath) ?? { entries: [] };
  const todayStart = new Date(new Date().toISOString().slice(0, 10)).getTime();
  const published_today  = hist.entries.filter(e => e.ts >= todayStart && e.action === "published").length;
  const cancelled_today  = hist.entries.filter(e => e.ts >= todayStart && e.action === "cancelled").length;
  const recent_posts     = hist.entries.filter(e => e.action === "published").slice(0, 10);

  // Fallback : compter via content_poller.log si historique vide
  let published_today_fallback = null;
  if (!existsSync(histPath)) {
    try {
      const log = readFileSync(`${WORKSPACE}/state/content_poller.log`, "utf8");
      published_today_fallback = (log.match(/\[canal\] ✅ Publié/g) ?? []).length;
    } catch {}
  }

  summaryCache = {
    ts: now,
    scrapers: {
      hourly_last_run: hourlyLastRun,
      daily_last_run:  dailyLastRun,
    },
    drafts,
    agents: agentStates,
    published: {
      today:             published_today,
      today_cancelled:   cancelled_today,
      recent:            recent_posts,
      log_count_fallback: published_today_fallback,  // non-null seulement si pas d'historique
    },
    today:  agg?.today  ?? null,
    month:  agg?.month  ?? null,
  };
  summaryCacheTs = now;
  res.json(summaryCache);
});

// History — posts publiés 30 jours
router.get("/history", (req, res) => {
  const now = Date.now();
  if (historyCache && now - historyCacheTs < HISTORY_TTL)
    return res.json(historyCache);

  const agg = readJSON(`${AGGREGATES}/content_daily.json`);
  if (agg?.history) {
    historyCache = { ts: now, history: agg.history };
    historyCacheTs = now;
    return res.json(historyCache);
  }

  // Fallback — lire content_publish_history.json
  const ph = readJSON(`${WORKSPACE}/state/content_publish_history.json`);
  const published = (ph?.entries ?? []).filter(e => e.action === "published");
  // Agréger par jour
  const byDay = {};
  for (const e of published) {
    const d = new Date(e.ts).toISOString().slice(0, 10);
    byDay[d] = (byDay[d] ?? 0) + 1;
  }
  const history = Object.entries(byDay)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-30)
    .map(([date, count]) => ({ date, published: count }));

  historyCache = { ts: now, history };
  historyCacheTs = now;
  res.json(historyCache);
});

export default router;
