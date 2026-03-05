import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "KILL_SWITCH_GUARDIAN", handler, argv: process.argv })
  .catch(e => { console.error("[KILL_SWITCH_GUARDIAN] fatal", e); process.exit(1); });
