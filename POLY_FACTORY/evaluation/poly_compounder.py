"""
POLY_COMPOUNDER — Nightly compound-learning agent for POLY_FACTORY.

Reads the day's audit log, extracts trade and risk events, calls Claude Haiku
to synthesise actionable lessons, and writes them to a dated JSON file under
state/memory/learnings/. Runs at 03:00 UTC as the first step of the nightly
evaluation cycle (before POLY_STRATEGY_EVALUATOR).

Output consumed by: POLY_STRATEGY_TUNER, strategy reactivation (Cycle 10).
"""

import json
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore


PRODUCER       = "POLY_COMPOUNDER"
LLM_MODEL      = "claude-haiku-4-5-20251001"
LLM_MAX_TOKENS = 512
LEARNINGS_DIR  = "memory/learnings"

# Audit topics that represent meaningful trading / risk events
TRADE_TOPICS = {
    "trade:paper_executed",
    "trade:live_executed",
    "trade:live_failed",
    "risk:kill_switch",
}


class PolyCompounder:
    """Extracts reusable lessons from daily trading activity via Haiku LLM."""

    def __init__(self, base_path="state", llm_client=None):
        self.store = PolyDataStore(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
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
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _today_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _collect_trades(self, audit_date_str: str | None = None) -> list:
        """Read the audit log for a date and return only trade/risk events.

        Args:
            audit_date_str: Date in YYYY_MM_DD format (underscores).
                            None = today.

        Returns:
            List of matching audit envelope dicts.
        """
        events = self.audit.read_events(audit_date_str)
        return [e for e in events if e.get("topic") in TRADE_TOPICS]

    def _build_prompt(self, trades: list) -> str:
        """Build the Haiku analysis prompt from a list of trade events."""
        # Group by strategy
        by_strategy: dict = {}
        for evt in trades:
            payload = evt.get("payload", {})
            strategy = payload.get("strategy", "GLOBAL")
            if strategy not in by_strategy:
                by_strategy[strategy] = {
                    "total": 0,
                    "executed": 0,
                    "failed": 0,
                    "kill_switch": 0,
                    "directions": set(),
                    "size_eur_total": 0.0,
                }
            entry = by_strategy[strategy]
            entry["total"] += 1
            topic = evt.get("topic", "")
            if topic in ("trade:paper_executed", "trade:live_executed"):
                entry["executed"] += 1
                size = payload.get("size_eur", 0.0) or 0.0
                entry["size_eur_total"] += float(size)
                direction = payload.get("direction", "")
                if direction:
                    entry["directions"].add(direction)
            elif topic == "trade:live_failed":
                entry["failed"] += 1
            elif topic == "risk:kill_switch":
                entry["kill_switch"] += 1

        # Serialise (sets → lists for JSON)
        summary_data = {}
        for strat, data in by_strategy.items():
            summary_data[strat] = {
                "total_events": data["total"],
                "executed": data["executed"],
                "failed": data["failed"],
                "kill_switch_triggered": data["kill_switch"],
                "directions_used": sorted(data["directions"]),
                "total_size_eur": round(data["size_eur_total"], 2),
            }

        summary_json = json.dumps(summary_data, indent=2)

        return (
            "You are a quantitative trading analyst reviewing a prediction-market system.\n"
            "Below is a JSON summary of today's trading activity grouped by strategy.\n\n"
            f"{summary_json}\n\n"
            "Analyse this data and extract actionable lessons for improving the system.\n"
            "Return a JSON object ONLY — no prose before or after — with this exact structure:\n"
            "{\n"
            '  "summary": "<one paragraph summarising today\'s activity>",\n'
            '  "lessons": [\n'
            '    {\n'
            '      "type": "pattern|risk|opportunity|warning",\n'
            '      "strategy": "<strategy name or null for global>",\n'
            '      "insight": "<specific, actionable observation>",\n'
            '      "confidence": "high|medium|low"\n'
            '    }\n'
            '  ]\n'
            "}"
        )

    def _call_llm(self, prompt: str) -> str:
        """Call Claude Haiku with the prompt and return the raw text response."""
        client = self._get_llm_client()
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _parse_response(
        self,
        raw: str,
        date_str: str,
        trade_count: int,
        strategies: list,
    ) -> dict:
        """Parse the LLM response into the full learnings envelope.

        Falls back gracefully if Haiku returns non-JSON text.
        """
        try:
            parsed = json.loads(raw)
            summary = parsed.get("summary", "")
            lessons = parsed.get("lessons", [])
        except json.JSONDecodeError:
            summary = raw
            lessons = []

        return {
            "date": date_str,
            "generated_at": self._now_utc(),
            "trades_analyzed": trade_count,
            "strategies_covered": strategies,
            "summary": summary,
            "lessons": lessons,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, date_str: str | None = None) -> dict:
        """Run the compound-learning cycle for a given date.

        Args:
            date_str: Target date in YYYY-MM-DD format. None = today UTC.

        Returns:
            The learnings dict that was persisted.
        """
        if date_str is None:
            date_str = self._today_utc()

        # Audit log uses underscores; file naming uses hyphens
        audit_date_str = date_str.replace("-", "_")

        trades = self._collect_trades(audit_date_str)

        # If no relevant activity today, persist a zero-lesson file — no LLM call
        if not trades:
            learnings = {
                "date": date_str,
                "generated_at": self._now_utc(),
                "trades_analyzed": 0,
                "strategies_covered": [],
                "summary": "No trading activity recorded for this date.",
                "lessons": [],
            }
            self.store.write_json(
                f"{LEARNINGS_DIR}/polymarket_{date_str}.json", learnings
            )
            return learnings

        # Derive strategy list
        strategies = sorted({
            t["payload"].get("strategy")
            for t in trades
            if t.get("payload", {}).get("strategy")
        })

        prompt  = self._build_prompt(trades)
        raw     = self._call_llm(prompt)
        learnings = self._parse_response(raw, date_str, len(trades), strategies)

        self.store.write_json(
            f"{LEARNINGS_DIR}/polymarket_{date_str}.json", learnings
        )
        return learnings

    def run_once(self) -> dict:
        """Convenience wrapper: run for today's UTC date."""
        return self.run()
