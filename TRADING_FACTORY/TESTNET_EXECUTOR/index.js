import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";
runAgent({ agentId: "TESTNET_EXECUTOR", handler, argv: process.argv })
  .catch(e => { console.error("[TESTNET_EXECUTOR] fatal", e); process.exit(1); });
