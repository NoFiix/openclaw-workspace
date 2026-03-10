import { Router } from "express";
import { readFileSync, existsSync } from "fs";
import { execSync } from "child_process";

const router = Router();

// Fallback sur les chemins réels si variables non chargées
const WORKSPACE  = process.env.WORKSPACE_DIR;
const AGGREGATES = process.env.AGGREGATES_DIR;

// Caches
let summaryCache = null; let summaryCacheTs = 0;
let historyCache = null; let historyCacheTs = 0;
const SUMMARY_TTL = 5 * 60_000;
const HISTORY_TTL = 15 * 60_000;

function readJSON(path) {
  try { return JSON.parse(readFileSync(path, "utf8")); }
  catch { return null; }
}

function dirSizeMB(path) {
  try {
    const out = execSync(`du -sm "${path}" 2>/dev/null | cut -f1`).toString().trim();
    return parseInt(out) || 0;
  } catch { return 0; }
}

function fileSizeMB(path) {
  try {
    const out = execSync(`du -sm "${path}" 2>/dev/null | cut -f1`).toString().trim();
    return parseInt(out) || 0;
  } catch { return 0; }
}

function getDisk() {
  try {
    const out = execSync("df / | tail -1").toString().trim().split(/\s+/);
    const total = parseInt(out[1]) / 1024;
    const used  = parseInt(out[2]) / 1024;
    const free  = parseInt(out[3]) / 1024;
    return {
      total_mb: Math.round(total),
      used_mb:  Math.round(used),
      free_mb:  Math.round(free),
      pct_used: Math.round(used / total * 100),
    };
  } catch { return null; }
}

router.get("/summary", (req, res) => {
  const now = Date.now();
  if (summaryCache && now - summaryCacheTs < SUMMARY_TTL)
    return res.json(summaryCache);

  const disk = getDisk();
  const sizes = {
    bus:         dirSizeMB(`${WORKSPACE}/state/trading/bus`),
    state:       dirSizeMB(`${WORKSPACE}/state`),
    agents:      dirSizeMB(`${WORKSPACE}/agents`),
    poller_log:  fileSizeMB(`${WORKSPACE}/state/trading/poller.log`),
    hourly_log:  fileSizeMB(`${WORKSPACE}/state/hourly_scraper.log`),
    aggregates:  dirSizeMB(AGGREGATES),
    workspace:   dirSizeMB(WORKSPACE),
  };

  summaryCache = { ts: now, disk, sizes };
  summaryCacheTs = now;
  res.json(summaryCache);
});

router.get("/history", (req, res) => {
  const now = Date.now();
  if (historyCache && now - historyCacheTs < HISTORY_TTL)
    return res.json(historyCache);

  const agg = readJSON(`${AGGREGATES}/storage_daily.json`);
  if (agg) {
    historyCache = { ts: now, history: agg.history ?? [] };
    historyCacheTs = now;
    return res.json(historyCache);
  }

  historyCache = { ts: now, history: [] };
  historyCacheTs = now;
  res.json(historyCache);
});

export default router;
