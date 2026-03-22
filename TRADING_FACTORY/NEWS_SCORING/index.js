import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "NEWS_SCORING", handler, argv: process.argv })
  .catch(e => { console.error("[NEWS_SCORING] fatal", e); process.exit(1); });
