import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "PAPER_EXECUTOR", handler, argv: process.argv })
  .catch(e => { console.error("[PAPER_EXECUTOR] fatal", e); process.exit(1); });
