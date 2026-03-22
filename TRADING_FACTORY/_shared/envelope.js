import { randomUUID } from "crypto";

/**
 * Fabrique un event envelope standard.
 * Tous les agents utilisent cette fonction — jamais de JSON brut.
 */
export function makeEvent({
  topic, type, producer,
  scope = {}, quality = {},
  payload = {}, causation_id = null
}) {
  return {
    event_id:  randomUUID(),
    ts:        Date.now(),
    topic,
    type,
    producer,
    trace: {
      trace_id:       randomUUID(),
      correlation_id: randomUUID(),
      causation_id:   causation_id ?? null,
    },
    scope: {
      env:      process.env.TRADING_ENV ?? "paper",
      chain:    "none",
      dex:      "none",
      exchange: "binance",
      account:  "main",
      asset:    "BTCUSDT",
      timeframe:"1m",
      ...scope,
    },
    quality:  { score: 1.0, flags: [], ...quality },
    privacy:  { contains_secrets: false, redactions: [] },
    payload,
  };
}
