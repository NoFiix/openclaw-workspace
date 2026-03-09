import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";
runAgent({ agentId: "TRADE_STRATEGY_TUNER", handler, argv: process.argv })
  .catch(e => { console.error("[TRADE_STRATEGY_TUNER] fatal", e); process.exit(1); });
