import { runAgent } from "../_shared/agentRuntime.js";
import { handler }  from "./handler.js";
runAgent({ agentId: "SYSTEM_WATCHDOG", handler, argv: process.argv });
