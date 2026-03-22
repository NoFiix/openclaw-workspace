import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "MARKET_EYE", handler, argv: process.argv })
  .catch(e => { console.error("[MARKET_EYE] fatal", e); process.exit(1); });
