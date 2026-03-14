"""
poly_log_tokens — Token cost tracker for POLY_FACTORY LLM calls.

Python equivalent of skills_custom/trading/_shared/logTokens.js.
Writes to state/llm/token_costs.jsonl with system="polymarket" so that
GLOBAL_TOKEN_TRACKER can aggregate POLY costs alongside trading costs.

Usage:
    from core.poly_log_tokens import log_tokens
    log_tokens(base_path, "POLY_MARKET_ANALYST", "claude-sonnet-4-6",
               response.usage.input_tokens, response.usage.output_tokens,
               task="resolution_parse")
"""

import json
import os
from datetime import datetime, timezone

# Prices in USD per million tokens (input, output)
_PRICES = {
    "claude-sonnet-4-6":          {"in": 3.00,  "out": 15.00},
    "claude-sonnet-4-20250514":   {"in": 3.00,  "out": 15.00},
    "claude-haiku-4-5-20251001":  {"in": 0.80,  "out": 4.00},
    "claude-opus-4-6":            {"in": 15.00, "out": 75.00},
    "claude-opus-4-20250514":     {"in": 15.00, "out": 75.00},
}
_DEFAULT_PRICE = {"in": 1.00, "out": 5.00}

TOKEN_COSTS_FILE = "llm/token_costs.jsonl"


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = _PRICES.get(model, _DEFAULT_PRICE)
    return round((input_tokens * p["in"] + output_tokens * p["out"]) / 1_000_000, 8)


def log_tokens(
    base_path: str,
    agent_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    task: str = "",
) -> None:
    """Append one token-cost record to state/llm/token_costs.jsonl.

    Failures are silently swallowed — never interrupt the calling agent.

    Args:
        base_path:     Absolute path to the POLY_FACTORY state directory.
        agent_id:      Agent name, e.g. "POLY_MARKET_ANALYST".
        model:         Model ID, e.g. "claude-sonnet-4-6".
        input_tokens:  Number of input tokens consumed.
        output_tokens: Number of output tokens consumed.
        task:          Optional label for the call type, e.g. "resolution_parse".
    """
    try:
        now = datetime.now(timezone.utc)
        entry = {
            "ts":       int(now.timestamp() * 1000),
            "date":     now.strftime("%Y-%m-%d"),
            "hour":     now.hour,
            "system":   "polymarket",
            "agent":    agent_id,
            "model":    model,
            "task":     task,
            "input":    input_tokens,
            "output":   output_tokens,
            "total":    input_tokens + output_tokens,
            "cost_usd": _calc_cost(model, input_tokens, output_tokens),
        }
        file_path = os.path.join(os.path.abspath(base_path), TOKEN_COSTS_FILE)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never interrupt the calling agent
