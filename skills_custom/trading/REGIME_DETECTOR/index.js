import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "REGIME_DETECTOR", handler, argv: process.argv })
  .catch(e => { console.error("[REGIME_DETECTOR] fatal", e); process.exit(1); });
