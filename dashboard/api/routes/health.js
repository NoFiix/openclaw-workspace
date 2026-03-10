import { Router } from "express";
import { readFileSync, existsSync } from "fs";
import { execSync } from "child_process";

const router = Router();
const STATE_DIR    = process.env.STATE_DIR    || "/home/openclawadmin/openclaw/workspace/state/trading";
const WORKSPACE    = process.env.WORKSPACE_DIR  || "/home/openclawadmin/openclaw/workspace";
const AGGREGATES   = process.env.AGGREGATES_DIR || "/home/openclawadmin/openclaw/dashboard-data/aggregates";

// Cache TTL 15s
let cache = null;
let cacheTs = 0;
const TTL = 15_000;

function readJSON(path) {
  try { return JSON.parse(readFileSync(path, "utf8")); }
  catch { return null; }
}

function getPollerPid(name) {
  try {
    const out = execSync(`pgrep -f "${name}" 2>/dev/null || echo ""`).toString().trim();
    return out ? parseInt(out.split("\n")[0]) : null;
  } catch { return null; }
}

function getDiskUsage() {
  try {
    const out = execSync("df -h / | tail -1").toString().trim().split(/\s+/);
    return { total: out[1], used: out[2], free: out[3], pct: out[4] };
  } catch { return null; }
}

router.get("/", (req, res) => {
  const now = Date.now();
  if (cache && now - cacheTs < TTL) return res.json(cache);

  // Watchdog state
  const watchdog = readJSON(`${STATE_DIR}/memory/SYSTEM_WATCHDOG.state.json`);
  const score    = watchdog?.metrics?.last_health_score ?? null;
  const crits    = watchdog?.metrics?.last_crit_count   ?? 0;
  const warns    = watchdog?.metrics?.last_warn_count   ?? 0;
  const incidents = Object.values(watchdog?.incidents ?? {})
    .filter(i => i.status === "open").length;

  // Pollers
  const tradingPid = getPollerPid("trading/poller.js");
  const contentPid = getPollerPid("skills_custom/poller.js");

  // Disk
  const disk = getDiskUsage();

  // Snapshot agrégat si dispo
  const snap = readJSON(`${AGGREGATES}/health_snapshot.json`);

  cache = {
    ts: now,
    score,
    crits,
    warns,
    open_incidents: incidents,
    pollers: {
      trading: { active: !!tradingPid, pid: tradingPid },
      content: { active: !!contentPid, pid: contentPid },
    },
    disk,
    last_watchdog_run: watchdog?.stats?.last_run_ts ?? null,
    snapshot: snap ?? null,
  };
  cacheTs = now;
  res.json(cache);
});

export default router;
