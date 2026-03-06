import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "PERFORMANCE_ANALYST", handler, argv: process.argv })
  .catch(e => { console.error("[PERFORMANCE_ANALYST] fatal", e); process.exit(1); });
