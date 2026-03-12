"""
POLY_STRATEGY_EVALUATOR — 8-axis scoring, verdicts, and strategy ranking.

Compares and ranks all paper-testing and live strategies on a 0–100 scale
using 8 weighted axes derived from resolved P&L metrics and account data.

8 axes (see references/evaluator_weights.json for weights and formulas):
  profitability  — total return % normalised
  win_rate       — win rate
  sharpe         — Sharpe ratio normalised
  profit_factor  — profit factor normalised
  drawdown       — max drawdown quality (inverted)
  tradability    — trade count with optional -15 backtest malus
  stability      — return stability (softer Sharpe curve)
  activity       — trade frequency

5 verdicts (from score):
  STAR      ≥ 75   — top-tier, ready for promotion
  SOLID     60–74  — good, promotable
  FRAGILE   40–59  — borderline, needs more data
  DECLINING 20–39  — performance degrading
  RETIRE     < 20  — below minimum, should be retired

Reads  : PolyPerformanceLogger metrics + PolyStrategyAccount
Writes : state/evaluation/strategy_scores.json
         state/evaluation/strategy_rankings.json
Emits  : eval:score_updated (bus + audit)
"""

from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_strategy_account import PolyStrategyAccount
from evaluation.poly_performance_logger import PolyPerformanceLogger


CONSUMER_ID = "POLY_STRATEGY_EVALUATOR"

# State files (relative to base_path)
SCORES_FILE   = "evaluation/strategy_scores.json"
RANKINGS_FILE = "evaluation/strategy_rankings.json"

# Axis weights (must sum to 1.0)
AXES_WEIGHTS = {
    "profitability":  0.20,
    "win_rate":       0.15,
    "sharpe":         0.20,
    "profit_factor":  0.15,
    "drawdown":       0.10,
    "tradability":    0.10,
    "stability":      0.05,
    "activity":       0.05,
}

# Verdict thresholds (from architecture examples: 78=STAR, 71/64=SOLID, 55/48/42=FRAGILE)
VERDICT_THRESHOLDS = [
    (75, "STAR"),
    (60, "SOLID"),
    (40, "FRAGILE"),
    (20, "DECLINING"),
    (0,  "RETIRE"),
]


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PolyStrategyEvaluator:
    """8-axis evaluator: scores strategies, assigns verdicts, ranks them."""

    def __init__(self, base_path="state"):
        self.base_path = base_path
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)

    # ------------------------------------------------------------------
    # Pure scoring helpers
    # ------------------------------------------------------------------

    def score_axes(
        self,
        metrics: dict,
        initial_capital: float,
        is_backtest: bool = False,
    ) -> dict:
        """Compute 8 axis scores from resolved-trade metrics.

        Pure function — no I/O, no side effects.

        Args:
            metrics:         Dict from PolyPerformanceLogger.compute_metrics():
                             {total_trades, win_rate, total_pnl, profit_factor,
                              sharpe_ratio, max_drawdown_eur}
            initial_capital: Strategy initial capital in EUR (for % calculations).
            is_backtest:     If True, apply -15 malus to tradability axis.

        Returns:
            Dict mapping each axis name to a float in [0, 100].
        """
        total_trades  = metrics.get("total_trades", 0)
        win_rate      = metrics.get("win_rate", 0.0)       # 0.0–1.0
        total_pnl     = metrics.get("total_pnl", 0.0)
        profit_factor = metrics.get("profit_factor", 0.0)
        sharpe_ratio  = metrics.get("sharpe_ratio", 0.0)
        max_dd_eur    = metrics.get("max_drawdown_eur", 0.0)

        # Derived percentages
        return_pct = (total_pnl / initial_capital * 100.0) if initial_capital > 0 else 0.0
        max_dd_pct = (max_dd_eur / initial_capital * 100.0) if initial_capital > 0 else 0.0

        # Axis scores
        profitability  = min(100.0, max(0.0, return_pct * 10.0))
        win_rate_score = win_rate * 100.0
        sharpe_score   = min(100.0, max(0.0, sharpe_ratio * 33.33))
        pf_score       = min(100.0, max(0.0, (profit_factor - 0.5) * 50.0))
        drawdown_score = max(0.0, 100.0 + max_dd_pct * 2.0)
        tradability    = min(100.0, total_trades * 2.0)
        if is_backtest:
            tradability = max(0.0, tradability - 15.0)
        stability      = min(100.0, max(0.0, sharpe_ratio * 16.67))
        activity       = min(100.0, total_trades * 2.0)

        return {
            "profitability":  round(profitability,  2),
            "win_rate":       round(win_rate_score, 2),
            "sharpe":         round(sharpe_score,   2),
            "profit_factor":  round(pf_score,       2),
            "drawdown":       round(drawdown_score, 2),
            "tradability":    round(tradability,    2),
            "stability":      round(stability,      2),
            "activity":       round(activity,       2),
        }

    def total_score(self, axes: dict) -> float:
        """Compute weighted total from axis scores.

        Args:
            axes: Dict of axis_name → score (0–100).

        Returns:
            Weighted total in [0, 100], rounded to 2 decimal places.
        """
        total = sum(axes[axis] * weight for axis, weight in AXES_WEIGHTS.items())
        return round(total, 2)

    def verdict_from_score(self, score: float) -> str:
        """Map a total score to a verdict string.

        Args:
            score: Weighted total in [0, 100].

        Returns:
            One of: STAR, SOLID, FRAGILE, DECLINING, RETIRE.
        """
        for threshold, verdict in VERDICT_THRESHOLDS:
            if score >= threshold:
                return verdict
        return "RETIRE"

    # ------------------------------------------------------------------
    # Evaluate + persist
    # ------------------------------------------------------------------

    def evaluate(
        self,
        strategy: str,
        account_id: str,
        metrics: dict,
        initial_capital: float,
        is_backtest: bool = False,
    ) -> dict:
        """Full evaluation pipeline for one strategy.

        Computes axis scores, total score, and verdict.  Persists to
        strategy_scores.json, rebuilds rankings, publishes eval:score_updated
        on the bus, and writes to the audit log.

        Args:
            strategy:        Strategy name (e.g. "POLY_ARB_SCANNER").
            account_id:      Full account ID (e.g. "ACC_POLY_ARB_SCANNER").
            metrics:         Dict from PolyPerformanceLogger.compute_metrics().
            initial_capital: Starting capital in EUR for % normalisation.
            is_backtest:     Apply backtest malus to tradability axis.

        Returns:
            Dict with: strategy, account_id, score_total, verdict,
            previous_score, previous_verdict, axes, evaluated_at.
        """
        axes      = self.score_axes(metrics, initial_capital, is_backtest)
        score     = self.total_score(axes)
        verdict   = self.verdict_from_score(score)
        now       = _now_utc()

        # Load previous scores for delta
        all_scores = self.store.read_json(SCORES_FILE) or {}
        prev_entry      = all_scores.get(strategy, {})
        previous_score  = prev_entry.get("score_total")
        previous_verdict = prev_entry.get("verdict")

        # Persist updated score entry
        all_scores[strategy] = {
            "account_id":    account_id,
            "score_total":   score,
            "verdict":       verdict,
            "axes":          axes,
            "evaluated_at":  now,
        }
        self.store.write_json(SCORES_FILE, all_scores)

        # Rebuild rankings
        self.update_rankings()

        result = {
            "strategy":        strategy,
            "account_id":      account_id,
            "score_total":     score,
            "verdict":         verdict,
            "previous_score":  previous_score,
            "previous_verdict": previous_verdict,
            "axes":            axes,
            "evaluated_at":    now,
        }

        # Publish bus event + audit
        payload = {
            "strategy":        strategy,
            "account_id":      account_id,
            "score_total":     score,
            "verdict":         verdict,
            "previous_score":  previous_score,
            "previous_verdict": previous_verdict,
            "axes":            axes,
        }
        self.bus.publish("eval:score_updated", CONSUMER_ID, payload)
        self.audit.log_event("eval:score_updated", CONSUMER_ID, payload)

        return result

    def update_rankings(self) -> list:
        """Rebuild strategy_rankings.json from all current score entries.

        Sorts all strategies by score_total descending, assigns rank 1..N.

        Returns:
            Sorted list of ranking dicts.
        """
        all_scores = self.store.read_json(SCORES_FILE) or {}
        ranked = sorted(
            all_scores.items(),
            key=lambda kv: kv[1].get("score_total", 0),
            reverse=True,
        )
        rankings = [
            {
                "rank":        i + 1,
                "strategy":    strategy,
                "account_id":  entry.get("account_id"),
                "score_total": entry.get("score_total"),
                "verdict":     entry.get("verdict"),
                "axes":        entry.get("axes"),
            }
            for i, (strategy, entry) in enumerate(ranked)
        ]
        self.store.write_json(RANKINGS_FILE, rankings)
        return rankings

    def get_scores(self) -> dict:
        """Return the full strategy_scores.json dict."""
        return self.store.read_json(SCORES_FILE) or {}

    def get_rankings(self) -> list:
        """Return the strategy_rankings.json list."""
        return self.store.read_json(RANKINGS_FILE) or []

    def run_once(self, strategies: list, is_backtest: bool = False) -> list:
        """Batch evaluation: load data and evaluate each listed strategy.

        For each strategy, loads the PolyStrategyAccount (for initial_capital)
        and PolyPerformanceLogger metrics, then calls evaluate().  Strategies
        whose account or P&L log cannot be found are skipped silently.

        Args:
            strategies:  List of strategy names (e.g. ["POLY_ARB_SCANNER"]).
            is_backtest: Apply backtest malus to all strategies in this run.

        Returns:
            List of evaluate() result dicts, one per successfully evaluated
            strategy.
        """
        logger = PolyPerformanceLogger(base_path=self.base_path)
        results = []

        for strategy in strategies:
            account_id = f"ACC_{strategy}"
            try:
                account = PolyStrategyAccount.load(account_id, self.base_path)
            except FileNotFoundError:
                continue  # Account not yet created — skip

            initial_capital = account.data["capital"]["initial"]
            metrics = logger.compute_metrics(strategy)

            if metrics["total_trades"] == 0:
                continue  # No trades yet — skip

            result = self.evaluate(
                strategy, account_id, metrics, initial_capital, is_backtest
            )
            results.append(result)

        return results
