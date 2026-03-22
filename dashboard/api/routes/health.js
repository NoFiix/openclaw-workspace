import { Router } from "express";
import { readFileSync, existsSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { execSync } from "child_process";

const router = Router();
const STATE_DIR    = process.env.STATE_DIR    || "/home/openclawadmin/openclaw/workspace/state/trading";
const WORKSPACE    = process.env.WORKSPACE_DIR  || "/home/openclawadmin/openclaw/workspace";
const AGGREGATES   = process.env.AGGREGATES_DIR || "/home/openclawadmin/openclaw/dashboard-data/aggregates";
const POLY_STATE   = process.env.POLY_BASE_PATH  || "/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state";

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

// Status based on schedule-aware staleness (same multipliers as SYSTEM_WATCHDOG)
function computeAgentStatus(lastRunTs, everySeconds) {
  if (!lastRunTs) return "unknown";
  const elapsed  = Math.floor(Date.now() / 1000) - lastRunTs;
  const interval = everySeconds || 600;
  if (elapsed < interval * 3)  return "ok";
  if (elapsed < interval * 10) return "warn";
  return "error";
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
  const tradingPid = getPollerPid("TRADING_FACTORY/poller.js");
  const contentPid = getPollerPid("CONTENT_FACTORY/poller.js");

  // Disk
  const disk = getDiskUsage();

  // Snapshot agrégat si dispo
  const snap = readJSON(`${AGGREGATES}/health_snapshot.json`);

  // ── Agents — scan dynamique state/trading/memory/ + content logs ─────────
  const allAgents = [];
  const memoryDir   = join(STATE_DIR, "memory");
  const schedulesDir = join(STATE_DIR, "schedules");

  // Charger tous les schedules en cache (agentId → every_seconds)
  const scheduleCache = {};
  if (existsSync(schedulesDir)) {
    try {
      readdirSync(schedulesDir)
        .filter(f => f.endsWith(".schedule.json"))
        .forEach(f => {
          const s = readJSON(join(schedulesDir, f));
          if (s?.agent_id) scheduleCache[s.agent_id] = s.every_seconds ?? null;
        });
    } catch {}
  }

  // Agents legacy à ignorer (state.json orphelins d'agents renommés ou supprimés)
  const LEGACY_SKIP = new Set(["STRATEGY_TUNER"]);

  // Agents trading/global/system — depuis state/trading/memory/*.state.json
  if (existsSync(memoryDir)) {
    try {
      readdirSync(memoryDir)
        .filter(f => f.endsWith(".state.json"))
        .forEach(f => {
          const name     = f.replace(".state.json", "");
          if (LEGACY_SKIP.has(name)) return; // fichier state orphelin, ignorer
          const state    = readJSON(join(memoryDir, f));
          const lastRun  = state?.stats?.last_run_ts ?? null;
          const interval = scheduleCache[name] ?? null;
          // Si agent désactivé dans le schedule, marquer disabled plutôt qu'error
          const schedFile = join(schedulesDir, `${name}.schedule.json`);
          const schedData = existsSync(schedFile) ? readJSON(schedFile) : null;
          const disabled  = schedData?.enabled === false;
          allAgents.push({
            name,
            last_run_ts:   lastRun,
            runs:          state?.stats?.runs   ?? 0,
            errors:        state?.stats?.errors ?? 0,
            every_seconds: interval,
            status:        disabled ? "disabled" : computeAgentStatus(lastRun, interval),
          });
        });
    } catch {}
  }

  // BINANCE_PRICE_FEED — fallback runs/ si pas de state.json dans memory/
  if (!allAgents.find(a => a.name === "BINANCE_PRICE_FEED")) {
    const runsDir = join(STATE_DIR, "runs");
    if (existsSync(runsDir)) {
      try {
        const files = readdirSync(runsDir).filter(f => f.startsWith("BINANCE_PRICE_FEED-"));
        if (files.length) {
          const last = files.sort()[files.length - 1];
          const ms   = parseInt(last.replace("BINANCE_PRICE_FEED-", "").replace(".json", ""));
          if (!isNaN(ms)) {
            const lastRun  = Math.floor(ms / 1000);
            const interval = scheduleCache["BINANCE_PRICE_FEED"] ?? 30;
            allAgents.push({ name: "BINANCE_PRICE_FEED", last_run_ts: lastRun, runs: 0, errors: 0, every_seconds: interval, status: computeAgentStatus(lastRun, interval) });
          }
        }
      } catch {}
    }
  }

  // Scripts content — depuis mtime des logs
  const contentLogDir = join(WORKSPACE, "state");
  const contentScripts = [
    { name: "hourly_scraper", log: "hourly_scraper.log", every: 3600  },
    { name: "daily_scraper",  log: "daily_scraper.log",  every: 86400 },
  ];
  for (const { name, log, every } of contentScripts) {
    const logPath = join(contentLogDir, log);
    if (existsSync(logPath)) {
      const mtime = Math.floor(statSync(logPath).mtimeMs / 1000);
      allAgents.push({ name, last_run_ts: mtime, every_seconds: every, status: computeAgentStatus(mtime, every) });
    } else {
      allAgents.push({ name, last_run_ts: null, every_seconds: every, status: "unknown" });
    }
  }

  // Pollers — depuis pgrep déjà calculé
  // "trading/poller.js" = System Pollers layer ; "content/poller.js" = System Pollers layer ; "poller.js" = Content Pipeline layer (même process)
  allAgents.push({ name: "TRADING_FACTORY/poller.js", last_run_ts: null, every_seconds: null, status: tradingPid ? "ok" : "error" });
  allAgents.push({ name: "content/poller.js", last_run_ts: null, every_seconds: null, status: contentPid ? "ok" : "error" });
  allAgents.push({ name: "poller.js",         last_run_ts: null, every_seconds: null, status: contentPid ? "ok" : "error" });

  // ── POLY_FACTORY orchestrateur ────────────────────────────────────────────
  const polySystemState = readJSON(join(POLY_STATE, "orchestrator/system_state.json"));
  const polyRiskState   = readJSON(join(POLY_STATE, "risk/global_risk_state.json"));
  const polyOrchestratorPid = getPollerPid("run_orchestrator.py");
  const polyGlobalRiskStatus = polyRiskState?.status ?? polySystemState?.global_risk_status ?? "NORMAL";
  const polyOrchestratorStatus = polyOrchestratorPid ? "ok"
    : polySystemState ? "warn"   // state exists but process not running
    : "unknown";

  const agentsOk      = allAgents.filter(a => a.status === "ok").length;
  const agentsWarn    = allAgents.filter(a => a.status === "warn").length;
  const agentsError   = allAgents.filter(a => a.status === "error").length;
  const agentsUnknown = allAgents.filter(a => a.status === "unknown").length;

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
    agents: allAgents,
    agents_summary: { total: allAgents.length, ok: agentsOk, warn: agentsWarn, error: agentsError, unknown: agentsUnknown },
    poly_orchestrator: {
      status:            polyOrchestratorStatus,
      pid:               polyOrchestratorPid,
      global_risk_status: polyGlobalRiskStatus,
      last_nightly_run:  polySystemState?.last_nightly_run ?? null,
    },
  };
  cacheTs = now;
  res.json(cache);
});

export default router;
