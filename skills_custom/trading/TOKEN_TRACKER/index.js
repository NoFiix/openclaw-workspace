import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "TOKEN_TRACKER", handler, argv: process.argv })
  .catch(e => { console.error("[TOKEN_TRACKER] fatal", e); process.exit(1); });
