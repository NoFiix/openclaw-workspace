/**
 * Trading Poller — Sprint 1
 * Lit les schedules et déclenche les agents toutes les N secondes.
 * Process séparé du content-poller (cpu_shares=2048 dans docker-compose).
 *
 * Usage : node poller.js
 * Env   : STATE_DIR, WORKSPACE_DIR, TRADING_ENV
 */

import fs   from "fs";
import path from "path";
import { spawn } from "child_process";
import { randomUUID } from "crypto";

const STATE_DIR     = process.env.STATE_DIR     ?? "/home/node/.openclaw/workspace/state/trading";
const WORKSPACE_DIR = process.env.WORKSPACE_DIR ?? "/home/node/.openclaw/workspace";
const TRADING_ENV   = process.env.TRADING_ENV   ?? "paper";

function nowSec()     { return Math.floor(Date.now() / 1000); }
function sleep(ms)    { return new Promise(r => setTimeout(r, ms)); }
function rInt(n)      { return Math.floor(Math.random() * n); }

function readJson(p, fallback = {}) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); }
  catch { return fallback; }
}

function writeJson(p, obj) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), "utf-8");
}

function loadSchedules() {
  const dir = path.join(STATE_DIR, "schedules");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter(f => f.endsWith(".schedule.json"))
    .map(f => readJson(path.join(dir, f)))
    .filter(s => s?.enabled && s?.mode === "poll");
}

function runAgent(agentId, runId) {
  return new Promise((resolve) => {
    const skillPath  = path.join(WORKSPACE_DIR, "TRADING_FACTORY", agentId, "index.js");
    const runsDir    = path.join(STATE_DIR, "runs");
    fs.mkdirSync(runsDir, { recursive: true });

    const payload    = { agent_id: agentId, run_id: runId, state_dir: STATE_DIR, workspace_dir: WORKSPACE_DIR };
    const payloadPath = path.join(runsDir, `${runId}.json`);
    writeJson(payloadPath, payload);

    if (!fs.existsSync(skillPath)) {
      console.log(`[poller] ⚠️  ${agentId} — skill not found (${skillPath}), skip`);
      return resolve({ ok: false, reason: "skill_not_found" });
    }

    const child = spawn("node", ["--experimental-vm-modules", skillPath, "--input", payloadPath], {
      env: { ...process.env, STATE_DIR, WORKSPACE_DIR, TRADING_ENV },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let settled = false;
    const settle = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(killTimer);
      resolve(result);
    };
    const killTimer = setTimeout(() => {
      try { child.kill("SIGKILL"); } catch {}
      settle({ ok: false, code: null, timeout: true });
    }, 35000);
    child.stdout?.pipe(process.stdout, { end: false });
    child.stderr?.pipe(process.stderr, { end: false });
    child.on("exit", (code) => settle({ ok: code === 0, code }));
    child.on("error", (err) => settle({ ok: false, code: null, error: err.message }));

  });
}

// ── Boucle principale ─────────────────────────────────────────────────────

async function main() {
  console.log(`[poller] 🚀 démarrage — env=${TRADING_ENV} state=${STATE_DIR}`);
  console.log(`[poller] workspace=${WORKSPACE_DIR}`);

  // Suivi du dernier run par agent
  const lastRun = {};

  while (true) {
    const schedules = loadSchedules();
    const t = nowSec();

    for (const sched of schedules) {
      const { agent_id, every_seconds, jitter_seconds = 0, critical = true } = sched;
      const last = lastRun[agent_id] ?? 0;
      const due  = (t - last) >= every_seconds;
      if (!due) continue;

      const jitter = jitter_seconds > 0 ? rInt(jitter_seconds * 1000) : 0;
      if (jitter) await sleep(jitter);

      const runId = `${agent_id}-${Date.now()}`;
      console.log(`[poller] ▶ ${agent_id} (run=${runId})`);

      let result;
      try { result = await runAgent(agent_id, runId); }
      catch (e) { if (critical) throw e; result = { ok: false, reason: e.message }; }
      lastRun[agent_id] = nowSec();

      if (!result.ok) {
        console.log(`[poller] ⚠️  ${agent_id} exit code=${result.code ?? result.reason}`);
      }
    }

    await sleep(800);
  }
}

main().catch(e => {
  console.error("[poller] FATAL", e);
  process.exit(1);
});
