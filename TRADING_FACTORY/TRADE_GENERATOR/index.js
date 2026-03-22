import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "TRADE_GENERATOR", handler, argv: process.argv })
  .catch(e => { console.error("[TRADE_GENERATOR] fatal", e); process.exit(1); });
