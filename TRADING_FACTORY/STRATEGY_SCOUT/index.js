import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "STRATEGY_SCOUT", handler, argv: process.argv })
  .catch(e => { console.error("[STRATEGY_SCOUT] fatal", e); process.exit(1); });
