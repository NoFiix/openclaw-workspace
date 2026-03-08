/**
 * logTokens v2 — module partagé de tracking des tokens LLM
 * Utilisé par trading ET content pipeline
 * Écrit dans state/trading/learning/token_costs.jsonl (fichier centralisé)
 */
import fs   from "fs";
import path from "path";

// Chemin centralisé — même fichier pour tous les systèmes
const CENTRAL_LOG = process.env.STATE_DIR
  ? path.join(process.env.STATE_DIR, "..", "trading", "learning", "token_costs.jsonl")
  : "/home/node/.openclaw/workspace/state/trading/learning/token_costs.jsonl";

export function logTokens(stateDir, agentId, model, usage, task = "", system = "trading") {
  try {
    const entry = {
      ts:       Date.now(),
      date:     new Date().toISOString().slice(0, 10),
      hour:     new Date().getUTCHours(),
      system,   // "trading" | "content"
      agent:    agentId,
      model,
      task,
      input:    usage?.input_tokens  ?? 0,
      output:   usage?.output_tokens ?? 0,
      total:    (usage?.input_tokens ?? 0) + (usage?.output_tokens ?? 0),
      cost_usd: calcCost(model, usage),
    };

    // Essayer le chemin central d'abord, sinon fallback local
    let file;
    try {
      file = CENTRAL_LOG;
      fs.mkdirSync(path.dirname(file), { recursive: true });
    } catch {
      file = stateDir
        ? path.join(stateDir, "learning", "token_costs.jsonl")
        : "/tmp/token_costs.jsonl";
      fs.mkdirSync(path.dirname(file), { recursive: true });
    }

    fs.appendFileSync(file, JSON.stringify(entry) + "\n");
  } catch {}
}

function calcCost(model, usage) {
  const input  = usage?.input_tokens  ?? 0;
  const output = usage?.output_tokens ?? 0;
  const PRICES = {
    "claude-haiku-4-5-20251001": { in: 0.80,  out: 4.00  },
    "claude-sonnet-4-20250514":  { in: 3.00,  out: 15.00 },
    "claude-opus-4-20250514":    { in: 15.00, out: 75.00 },
    "gpt-4o":                    { in: 2.50,  out: 10.00 },
    "gpt-4o-mini":               { in: 0.15,  out: 0.60  },
  };
  const p = PRICES[model] ?? { in: 1.00, out: 5.00 };
  return parseFloat(((input * p.in + output * p.out) / 1_000_000).toFixed(8));
}
