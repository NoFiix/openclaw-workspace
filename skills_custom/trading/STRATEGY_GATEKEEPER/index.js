import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";
runAgent({ agentId: "STRATEGY_GATEKEEPER", handler, argv: process.argv })
  .catch(e => { console.error("[STRATEGY_GATEKEEPER] fatal", e); process.exit(1); });
