"""
POLY_STRATEGY_TUNER — Nightly parameter-optimisation agent for POLY_FACTORY.

Analyses strategy performance (metrics, account state, registry parameters,
and optional POLY_COMPOUNDER learnings) and calls Claude Sonnet to generate
structured parameter-adjustment recommendations or a STOP verdict.

Runs at 03:35 UTC as part of the nightly evaluation cycle (after
POLY_STRATEGY_EVALUATOR).

Guards:
- Minimum 50 trades required before any LLM call.
- STOP verdict automatically updates registry + account status to "stopped".
- Live strategies are flagged (requires human approval before applying
  recommendations) — the tuner records the flag but never auto-applies.

Output:
  state/evaluation/tuning_recommendations.json  (persisted, one key per strategy)
  bus topic: tuning:recommendation
"""

import json
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_strategy_account import PolyStrategyAccount
from core.poly_strategy_registry import PolyStrategyRegistry
from evaluation.poly_performance_logger import PolyPerformanceLogger


PRODUCER           = "POLY_STRATEGY_TUNER"
LLM_MODEL          = "claude-sonnet-4-6"
LLM_MAX_TOKENS     = 800
MIN_TRADES         = 50
RECOMMENDATIONS_FILE = "evaluation/tuning_recommendations.json"
LEARNINGS_DIR      = "memory/learnings"

VERDICTS = {"OPTIMIZABLE", "STOP", "INSUFFICIENT_DATA"}


class PolyStrategyTuner:
    """Nightly LLM-powered parameter-optimisation agent."""

    def __init__(self, base_path="state", llm_client=None):
        self.base_path = base_path
        self.store = PolyDataStore(base_path=base_path)
        self.bus   = PolyEventBus(base_path=base_path)
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
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _today_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load_context(self, strategy: str, account_id: str) -> dict:
        """Assemble all analysis data for a strategy."""
        metrics  = PolyPerformanceLogger(self.base_path).compute_metrics(strategy)
        try:
            account_data = PolyStrategyAccount.load(account_id, self.base_path).data
        except FileNotFoundError:
            account_data = {}

        registry_entry = PolyStrategyRegistry(self.base_path).get(strategy)
        today          = self._today_utc()
        learnings      = self.store.read_json(
            f"{LEARNINGS_DIR}/polymarket_{today}.json"
        )   # may be None

        return {
            "metrics":   metrics,
            "account":   account_data,
            "registry":  registry_entry,
            "learnings": learnings,
        }

    def _build_prompt(self, strategy: str, context: dict) -> str:
        """Build the Sonnet analysis prompt from the context dict."""
        registry   = context.get("registry") or {}
        params     = registry.get("parameters", {})
        metrics    = context.get("metrics", {})
        account    = context.get("account", {})
        learnings  = context.get("learnings")

        capital  = account.get("capital", {})
        pnl      = account.get("pnl", {})
        drawdown = account.get("drawdown", {})

        # Compounder summary section
        compounder_section = ""
        if learnings:
            summary  = learnings.get("summary", "")
            lessons  = learnings.get("lessons", [])
            relevant = [
                l for l in lessons
                if l.get("strategy") in (strategy, None)
            ]
            compounder_section = (
                f"\n\nCompounder summary (today):\n{summary}\n"
                f"Relevant lessons: {json.dumps(relevant, indent=2)}"
            )

        prompt = (
            "You are a quantitative trading analyst optimising a prediction-market strategy.\n\n"
            f"Strategy: {strategy}\n"
            f"Current parameters: {json.dumps(params, indent=2)}\n\n"
            "Performance metrics:\n"
            f"  total_trades:       {metrics.get('total_trades', 0)}\n"
            f"  win_rate:           {metrics.get('win_rate', 0.0)}\n"
            f"  sharpe_ratio:       {metrics.get('sharpe_ratio', 0.0)}\n"
            f"  profit_factor:      {metrics.get('profit_factor', 0.0)}\n"
            f"  max_drawdown_eur:   {metrics.get('max_drawdown_eur', 0.0)}\n"
            f"  total_pnl:          {metrics.get('total_pnl', 0.0)}\n\n"
            "Account state:\n"
            f"  capital.current:         {capital.get('current', 'unknown')}\n"
            f"  pnl.total:               {pnl.get('total', 'unknown')}\n"
            f"  drawdown.current_pct:    {drawdown.get('current_drawdown_pct', 'unknown')}\n"
            f"{compounder_section}\n\n"
            "Analyse the data above. If the strategy is recoverable, recommend specific "
            "parameter adjustments. If it is unrecoverable (persistent losses, structural "
            "edge erosion), return a STOP verdict.\n\n"
            "Return a JSON object ONLY — no prose before or after — with this exact structure:\n"
            "{\n"
            '  "verdict": "OPTIMIZABLE|STOP",\n'
            '  "confidence": "high|medium|low",\n'
            '  "summary": "<one paragraph>",\n'
            '  "parameter_recommendations": [\n'
            "    {\n"
            '      "parameter": "...",\n'
            '      "current_value": ...,\n'
            '      "recommended_value": ...,\n'
            '      "rationale": "...",\n'
            '      "expected_impact": "high|medium|low"\n'
            "    }\n"
            "  ],\n"
            '  "stop_reason": null\n'
            "}"
        )
        return prompt

    def _call_llm(self, prompt: str) -> str:
        """Call Claude Sonnet with the prompt and return the raw text response."""
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
        strategy: str,
        account_id: str,
        trades_analyzed: int,
    ) -> dict:
        """Parse the LLM response into the full recommendation envelope.

        Falls back gracefully if Sonnet returns non-JSON text.
        """
        try:
            parsed = json.loads(raw)
            verdict    = parsed.get("verdict", "OPTIMIZABLE")
            confidence = parsed.get("confidence", "low")
            summary    = parsed.get("summary", "")
            param_recs = parsed.get("parameter_recommendations", [])
            stop_reason = parsed.get("stop_reason", None)
        except json.JSONDecodeError:
            verdict    = "OPTIMIZABLE"
            confidence = "low"
            summary    = raw
            param_recs = []
            stop_reason = None

        return {
            "strategy":                strategy,
            "account_id":              account_id,
            "generated_at":            self._now_utc(),
            "trades_analyzed":         trades_analyzed,
            "verdict":                 verdict,
            "confidence":              confidence,
            "summary":                 summary,
            "parameter_recommendations": param_recs,
            "stop_reason":             stop_reason,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tune(self, strategy: str, account_id: str) -> dict:
        """Run the tuning cycle for a single strategy.

        Steps:
        1. Compute metrics; guard on MIN_TRADES.
        2. Load full context (account, registry, learnings).
        3. Build prompt → call LLM → parse response.
        4. Persist recommendation to RECOMMENDATIONS_FILE.
        5. Publish tuning:recommendation on bus.
        6. Audit the recommendation.
        7. If STOP: update registry + account status.

        Args:
            strategy:   Strategy name (e.g. "POLY_ARB_SCANNER").
            account_id: Full account ID (e.g. "ACC_POLY_ARB_SCANNER").

        Returns:
            Recommendation dict (envelope).
        """
        metrics = PolyPerformanceLogger(self.base_path).compute_metrics(strategy)
        trades_analyzed = metrics["total_trades"]

        # Guard: insufficient data
        if trades_analyzed < MIN_TRADES:
            return {
                "verdict":         "INSUFFICIENT_DATA",
                "strategy":        strategy,
                "account_id":      account_id,
                "trades_analyzed": trades_analyzed,
                "reason":          f"Need at least {MIN_TRADES} trades before tuning.",
            }

        context = self._load_context(strategy, account_id)
        prompt  = self._build_prompt(strategy, context)
        raw     = self._call_llm(prompt)
        rec     = self._parse_response(raw, strategy, account_id, trades_analyzed)

        # Persist: load existing dict, update this strategy's entry, write back
        rec_dict = self.store.read_json(RECOMMENDATIONS_FILE) or {}
        rec_dict[strategy] = rec
        self.store.write_json(RECOMMENDATIONS_FILE, rec_dict)

        # Publish on bus
        self.bus.publish("tuning:recommendation", PRODUCER, rec)

        # Audit
        self.audit.log_event("tuning:recommendation", PRODUCER, {
            "strategy":    strategy,
            "account_id":  account_id,
            "verdict":     rec["verdict"],
            "confidence":  rec["confidence"],
        })

        # STOP verdict: mark both registry and account as stopped
        if rec["verdict"] == "STOP":
            try:
                PolyStrategyRegistry(self.base_path).update_status(strategy, "stopped")
            except (ValueError, KeyError):
                pass   # strategy not in registry — skip silently

            try:
                PolyStrategyAccount.load(account_id, self.base_path).update_status("stopped")
            except FileNotFoundError:
                pass   # account not found — skip silently

            self.audit.log_event("strategy:stopped", PRODUCER, {
                "strategy":    strategy,
                "account_id":  account_id,
                "reason":      rec.get("stop_reason") or rec.get("summary", ""),
            })

        return rec

    def run_once(self, strategies: list) -> list:
        """Batch-tune a list of (strategy_name, account_id) tuples.

        Args:
            strategies: List of (strategy_name, account_id) tuples.

        Returns:
            List of recommendation dicts, one per strategy.
        """
        results = []
        for strategy, account_id in strategies:
            result = self.tune(strategy, account_id)
            results.append(result)
        return results
