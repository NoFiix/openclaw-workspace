import { FileBus }                       from "./bus.js";
import { makeEvent }                     from "./envelope.js";
import { loadState, saveState, loadConfig } from "./state.js";
import fs   from "fs";

/**
 * Runtime commun à tous les agents.
 * Charge state + config, crée le bus, exécute le handler, sauvegarde le state.
 */
export async function runAgent({ agentId, handler, argv }) {
  const inputIdx = argv.indexOf("--input");
  if (inputIdx === -1) throw new Error("Missing --input <path>");

  const inputPath  = argv[inputIdx + 1];
  const runPayload = JSON.parse(fs.readFileSync(inputPath, "utf-8"));

  const stateDir = runPayload.state_dir;
  const { state, path: statePath } = loadState(stateDir, agentId);
  const config = loadConfig(stateDir, agentId);
  const bus    = new FileBus(stateDir);

  /** Contexte injecté dans chaque handler */
  const ctx = {
    agentId,
    runId:    runPayload.run_id,
    stateDir,
    config,
    state,
    bus,

    /** Log formaté */
    log: (msg) => console.log(`[${agentId}][${new Date().toISOString()}] ${msg}`),

    /** Émet un event sur le bus et le retourne */
    emit: (topic, type, scope, payload, causation_id = null) => {
      const evt = makeEvent({
        topic, type,
        producer: { agent_id: agentId, run_id: runPayload.run_id, version: "1.0.0" },
        scope, payload, causation_id,
      });
      bus.publish(topic, evt);
      return evt;
    },
  };

  try {
    await handler(ctx);
    state.stats.runs        = (state.stats.runs ?? 0) + 1;
    state.stats.last_run_ts = Math.floor(Date.now() / 1000);
    saveState(statePath, state);
    process.exit(0);
  } catch (e) {
    state.stats.errors      = (state.stats.errors ?? 0) + 1;
    state.stats.last_run_ts = Math.floor(Date.now() / 1000);
    saveState(statePath, state);
    console.error(`[${agentId}] FATAL: ${e.message}`);
    console.error(e.stack);
    process.exit(1);
  }
}
