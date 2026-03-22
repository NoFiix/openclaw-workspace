import fs   from "fs";
import path from "path";

const DEFAULT_STATE = (agentId) => ({
  agent_id: agentId,
  version:  1,
  cursors:  {},
  cache:    {},
  stats:    { runs: 0, errors: 0, last_run_ts: 0 },
});

export function loadState(stateDir, agentId) {
  const p = path.join(stateDir, "memory", `${agentId}.state.json`);
  if (!fs.existsSync(p)) return { state: DEFAULT_STATE(agentId), path: p };
  try {
    return { state: JSON.parse(fs.readFileSync(p, "utf-8")), path: p };
  } catch {
    return { state: DEFAULT_STATE(agentId), path: p };
  }
}

export function saveState(statePath, state) {
  fs.mkdirSync(path.dirname(statePath), { recursive: true });
  fs.writeFileSync(statePath, JSON.stringify(state, null, 2), "utf-8");
}

export function loadConfig(stateDir, agentId) {
  const p = path.join(stateDir, "configs", `${agentId}.config.json`);
  if (!fs.existsSync(p)) return {};
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); }
  catch { return {}; }
}
