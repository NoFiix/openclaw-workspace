import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";
runAgent({ agentId: "TRADING_ORCHESTRATOR", handler, argv: process.argv })
  .catch(e => { console.error("[TRADING_ORCHESTRATOR] fatal", e); process.exit(1); });
