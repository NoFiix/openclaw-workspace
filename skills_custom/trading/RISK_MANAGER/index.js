import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "RISK_MANAGER", handler, argv: process.argv })
  .catch(e => { console.error("[RISK_MANAGER] fatal", e); process.exit(1); });
