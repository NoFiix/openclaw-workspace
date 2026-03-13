import { runAgent } from '../_shared/agentRuntime.js';
import { handler  } from './handler.js';

runAgent({ agentId: 'POLY_TRADING_PUBLISHER', handler, argv: process.argv })
  .catch(e => { console.error('[POLY_TRADING_PUBLISHER] fatal', e); process.exit(1); });
