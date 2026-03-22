import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";
runAgent({ agentId: "POLICY_ENGINE", handler, argv: process.argv })
  .catch(e => { console.error("[POLICY_ENGINE] fatal", e); process.exit(1); });
