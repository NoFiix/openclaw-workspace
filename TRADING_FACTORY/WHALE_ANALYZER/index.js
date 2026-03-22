import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";
runAgent({ agentId: "WHALE_ANALYZER", handler, argv: process.argv })
  .catch(e => { console.error("[WHALE_ANALYZER] fatal", e); process.exit(1); });
