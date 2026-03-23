/**
 * logTokens v3 — module partagé de tracking des tokens LLM
 * Utilise stateDir passé en paramètre (pas process.env)
 */
import fs   from "fs";
import path from "path";

export function logTokens(stateDir, agentId, model, usage, task = "", system = "trading") {
  try {
    if (!stateDir) return; // Pas de stateDir = on ignore silencieusement

    const entry = {
      ts:       Date.now(),
      date:     new Date().toISOString().slice(0, 10),
      hour:     new Date().getUTCHours(),
      system,
      agent:    agentId,
      model,
      task,
      input:    usage?.input_tokens  ?? 0,
      output:   usage?.output_tokens ?? 0,
      cache_read:     usage?.cache_read_input_tokens    ?? 0,
      cache_creation: usage?.cache_creation_input_tokens ?? 0,
      total:    (usage?.input_tokens ?? 0) + (usage?.output_tokens ?? 0),
      cost_usd: calcCost(model, usage),
    };

    // stateDir = .../state/trading — on écrit dans learning/
    const file = path.join(stateDir, "learning", "token_costs.jsonl");
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.appendFileSync(file, JSON.stringify(entry) + "\n");
  } catch {}
}

function calcCost(model, usage) {
  const input       = usage?.input_tokens                ?? 0;
  const output      = usage?.output_tokens               ?? 0;
  const cacheRead   = usage?.cache_read_input_tokens     ?? 0;
  const cacheCreate = usage?.cache_creation_input_tokens  ?? 0;
  const PRICES = {
    "claude-haiku-4-5-20251001": { in: 0.80,  out: 4.00  },
    "claude-sonnet-4-6":         { in: 3.00,  out: 15.00 },
    "claude-sonnet-4-20250514":  { in: 3.00,  out: 15.00 },
    "claude-opus-4-6":           { in: 15.00, out: 75.00 },
    "claude-opus-4-20250514":    { in: 15.00, out: 75.00 },
    "gpt-4o":                    { in: 2.50,  out: 10.00 },
    "gpt-4o-mini":               { in: 0.15,  out: 0.60  },
  };
  const p = PRICES[model] ?? { in: 1.00, out: 5.00 };
  // Cache read = 10% of input price, cache creation = 125% of input price
  const cost = (input * p.in + output * p.out + cacheRead * p.in * 0.1 + cacheCreate * p.in * 1.25) / 1_000_000;
  return parseFloat(cost.toFixed(8));
}
