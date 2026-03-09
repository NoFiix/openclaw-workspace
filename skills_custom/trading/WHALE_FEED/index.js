import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";
runAgent({ agentId: "WHALE_FEED", handler, argv: process.argv })
  .catch(e => { console.error("[WHALE_FEED] fatal", e); process.exit(1); });
