"""
POLY_STRATEGY_SCOUT — Weekly strategy-discovery agent for POLY_FACTORY.

Receives candidate strategy concepts, calls Claude Sonnet to evaluate each
for viability on the target platform(s), and persists results to
state/research/scouted_strategies.json.

Guards:
- Max 5 new evaluations per run (MAX_NEW_PER_RUN).
- Already-scouted candidates are skipped (dedup by name).
- Candidates targeting unavailable platforms are skipped.
- Scout NEVER registers or activates strategies — proposes only.

Output:
  state/research/scouted_strategies.json  (one key per scouted strategy)
  bus topic: scout:new_strategy_found     (for candidates with score ≥ 40)

Runs at: Sunday 08:00 UTC (Cycle 1 — Discovery).
"""

import json
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus


PRODUCER            = "POLY_STRATEGY_SCOUT"
LLM_MODEL           = "claude-sonnet-4-6"
LLM_MAX_TOKENS      = 800
MIN_VIABILITY_SCORE = 40
MAX_NEW_PER_RUN     = 5
SCOUTED_FILE        = "research/scouted_strategies.json"

VERDICTS = {"VIABLE", "MARGINAL", "NOT_VIABLE"}


class PolyStrategyScout:
    """Weekly LLM-powered strategy-discovery and viability-evaluation agent."""

    def __init__(self, base_path="state", llm_client=None):
        self.base_path = base_path
        self.store     = PolyDataStore(base_path=base_path)
        self.bus       = PolyEventBus(base_path=base_path)
        self.audit     = PolyAuditLog(base_path=base_path)
        self._llm_client = llm_client   # injectable; None → lazy anthropic.Anthropic()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_llm_client(self):
        """Return the LLM client, instantiating lazily if none was injected."""
        if self._llm_client is None:
            import anthropic  # deferred — avoids import error in test environments
            self._llm_client = anthropic.Anthropic()
        return self._llm_client

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _build_prompt(self, candidate: dict, available_connectors: list) -> str:
        """Build the Sonnet evaluation prompt for a single strategy candidate."""
        return (
            "You are a quantitative trading analyst evaluating a new strategy concept "
            "for a prediction-market trading system.\n\n"
            f"Strategy name: {candidate['name']}\n"
            f"Description:   {candidate['description']}\n"
            f"Category:      {candidate['category']}\n"
            f"Target platform: {candidate['platform']}\n"
            f"Proposed parameters: {json.dumps(candidate.get('proposed_parameters', {}), indent=2)}\n"
            f"Available connectors: {available_connectors}\n\n"
            "Evaluate the viability of this strategy for prediction-market trading. "
            "Consider: edge sustainability, data requirements, execution complexity, "
            "risk profile, and alignment with available platforms.\n\n"
            "Return a JSON object ONLY — no prose before or after — with this exact structure:\n"
            "{\n"
            '  "viability_score": <integer 0-100>,\n'
            '  "verdict": "VIABLE|MARGINAL|NOT_VIABLE",\n'
            '  "confidence": "high|medium|low",\n'
            '  "summary": "<one paragraph>",\n'
            '  "edge_source": "<information_asymmetry|liquidity|arbitrage|momentum|event>",\n'
            '  "risks": ["<risk1>", "<risk2>"],\n'
            '  "suggested_parameters": {}\n'
            "}"
        )

    def _call_llm(self, prompt: str) -> str:
        """Call Claude Sonnet with the prompt and return the raw text response."""
        client = self._get_llm_client()
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _parse_response(self, raw: str, candidate: dict) -> dict:
        """Parse the LLM response into a full scouted entry.

        Falls back gracefully on non-JSON responses.
        """
        try:
            parsed = json.loads(raw)
            viability_score    = int(parsed.get("viability_score", 0))
            verdict            = parsed.get("verdict", "NOT_VIABLE")
            confidence         = parsed.get("confidence", "low")
            summary            = parsed.get("summary", "")
            edge_source        = parsed.get("edge_source", "")
            risks              = parsed.get("risks", [])
            suggested_params   = parsed.get("suggested_parameters", {})
        except (json.JSONDecodeError, ValueError):
            viability_score  = 0
            verdict          = "NOT_VIABLE"
            confidence       = "low"
            summary          = raw
            edge_source      = ""
            risks            = []
            suggested_params = {}

        # Normalise verdict to known set
        if verdict not in VERDICTS:
            verdict = "NOT_VIABLE"

        flagged_for_human = viability_score >= MIN_VIABILITY_SCORE

        return {
            "name":                 candidate["name"],
            "description":          candidate.get("description", ""),
            "category":             candidate.get("category", ""),
            "platform":             candidate.get("platform", ""),
            "proposed_parameters":  candidate.get("proposed_parameters", {}),
            "scouted_at":           self._now_utc(),
            "viability_score":      viability_score,
            "verdict":              verdict,
            "confidence":           confidence,
            "summary":              summary,
            "edge_source":          edge_source,
            "risks":                risks,
            "suggested_parameters": suggested_params,
            "flagged_for_human":    flagged_for_human,
            "status":               "pending_human" if flagged_for_human else "rejected",
        }

    def _evaluate_candidate(self, candidate: dict, available_connectors: list) -> dict:
        """Evaluate a single candidate via LLM and return the scouted entry."""
        prompt = self._build_prompt(candidate, available_connectors)
        raw    = self._call_llm(prompt)
        return self._parse_response(raw, candidate)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(
        self,
        candidates: list,
        available_connectors: list = None,
        stopped_strategies: list = None,
    ) -> dict:
        """Run the weekly discovery cycle.

        Args:
            candidates: List of candidate dicts (name, description, category,
                        platform, proposed_parameters).
            available_connectors: List of active connector names (default: ["polymarket"]).
            stopped_strategies: Optional list of stopped strategy names for
                                Cycle 10 reactivation check. No LLM call.

        Returns:
            Dict with:
              - "evaluated":               list of scouted entry dicts
              - "flagged_count":           number of candidates flagged for human
              - "reactivation_candidates": list of stopped strategy names to recheck
        """
        if available_connectors is None:
            available_connectors = ["polymarket"]
        if stopped_strategies is None:
            stopped_strategies = []

        # Load existing scouted strategies (dedup source)
        existing = self.store.read_json(SCOUTED_FILE) or {}

        # Filter candidates: skip already-scouted and unavailable platforms
        to_evaluate = []
        for c in candidates:
            name     = c.get("name", "")
            platform = c.get("platform", "any")
            if name in existing:
                continue
            if platform != "any" and platform not in available_connectors:
                continue
            to_evaluate.append(c)

        # Respect weekly cap
        to_evaluate = to_evaluate[:MAX_NEW_PER_RUN]

        # Evaluate each candidate
        evaluated = []
        for candidate in to_evaluate:
            entry = self._evaluate_candidate(candidate, available_connectors)
            evaluated.append(entry)

            # Flag viable candidates for human review
            if entry["flagged_for_human"]:
                payload = {
                    "name":            entry["name"],
                    "viability_score": entry["viability_score"],
                    "verdict":         entry["verdict"],
                    "category":        entry["category"],
                    "platform":        entry["platform"],
                    "scouted_at":      entry["scouted_at"],
                }
                self.bus.publish("scout:new_strategy_found", PRODUCER, payload)
                self.audit.log_event("scout:new_strategy_found", PRODUCER, payload)

        # Persist all evaluated results
        for entry in evaluated:
            existing[entry["name"]] = entry
        if evaluated:
            self.store.write_json(SCOUTED_FILE, existing)

        # Reactivation candidates: stopped strategies not already fully evaluated
        reactivation_candidates = [
            name for name in stopped_strategies
            if name not in existing
        ]

        return {
            "evaluated":               evaluated,
            "flagged_count":           sum(1 for e in evaluated if e["flagged_for_human"]),
            "reactivation_candidates": reactivation_candidates,
        }
