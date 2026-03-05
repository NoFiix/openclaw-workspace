import { runAgent } from "../_shared/agentRuntime.js";
import { handler  } from "./handler.js";

runAgent({ agentId: "BINANCE_PRICE_FEED", handler, argv: process.argv })
  .catch(e => { console.error("[BINANCE_PRICE_FEED] fatal", e); process.exit(1); });
