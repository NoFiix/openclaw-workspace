import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "TRADING_PUBLISHER", handler, argv: process.argv })
  .catch(e => { console.error("[TRADING_PUBLISHER] fatal", e); process.exit(1); });
