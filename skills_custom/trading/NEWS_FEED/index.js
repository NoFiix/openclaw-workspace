import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "NEWS_FEED", handler, argv: process.argv })
  .catch(e => { console.error("[NEWS_FEED] fatal", e); process.exit(1); });
