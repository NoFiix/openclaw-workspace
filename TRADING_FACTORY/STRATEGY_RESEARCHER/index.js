import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "STRATEGY_RESEARCHER", handler, argv: process.argv })
  .catch(e => { console.error("[STRATEGY_RESEARCHER] fatal", e); process.exit(1); });
