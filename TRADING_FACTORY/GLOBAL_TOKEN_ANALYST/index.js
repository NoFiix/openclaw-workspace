import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "GLOBAL_TOKEN_ANALYST", handler, argv: process.argv })
  .catch(e => { console.error("[TOKEN_ANALYST] fatal", e); process.exit(1); });
