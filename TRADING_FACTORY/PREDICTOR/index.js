import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "PREDICTOR", handler, argv: process.argv })
  .catch(e => { console.error("[PREDICTOR] fatal", e); process.exit(1); });
