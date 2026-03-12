"""
POLY_PERFORMANCE_LOGGER — Per-strategy trade P&L aggregation and metrics.

Maintains a per-strategy P&L log and computes six financial metrics:
  - total_trades     : number of resolved trades
  - win_rate         : fraction of trades with pnl > 0
  - total_pnl        : sum of all P&L (EUR)
  - profit_factor    : gross_profit / gross_loss (0.0 if no losses)
  - sharpe_ratio     : mean(PnL) / std(PnL) * sqrt(n)
  - max_drawdown_eur : peak-to-trough drawdown (≤ 0)

Writes aggregated stats to dashboard-data/aggregates/ for the dashboard.
Publishes eval:milestone when total_trades crosses a milestone threshold
(50, 100, 200, 500, 1 000).

Called by the orchestrator after trade resolution — not by reading the
execution log (which records entry costs, not resolved P&L).

State written:
  {base_path}/trading/positions_by_strategy/{strategy}_pnl.jsonl
  {dashboard_path}/aggregates/poly_paper_stats.json
  {dashboard_path}/aggregates/poly_live_stats.json
"""

import json
import math
import os
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus


CONSUMER_ID = "POLY_PERFORMANCE_LOGGER"

# Trade count thresholds that trigger an eval:milestone bus event
MILESTONE_COUNTS = [50, 100, 200, 500, 1000]

# P&L log directory (relative to base_path)
PNL_LOG_DIR = "trading/positions_by_strategy"

# Dashboard stats files (relative to dashboard_path)
PAPER_STATS_FILE = "aggregates/poly_paper_stats.json"
LIVE_STATS_FILE  = "aggregates/poly_live_stats.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_sharpe(pnl_series: list) -> float:
    """mean(PnL) / std(PnL) * sqrt(n).  Returns 0.0 if n < 2 or std == 0."""
    n = len(pnl_series)
    if n < 2:
        return 0.0
    mean = sum(pnl_series) / n
    variance = sum((p - mean) ** 2 for p in pnl_series) / (n - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(n)


def _compute_max_drawdown(pnl_series: list) -> float:
    """Max peak-to-trough drawdown (≤ 0) from the equity curve."""
    if not pnl_series:
        return 0.0
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for pnl in pnl_series:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = equity - peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


class PolyPerformanceLogger:
    """Per-strategy trade P&L aggregation, metrics, and milestone detection."""

    def __init__(self, base_path="state", dashboard_path="dashboard-data"):
        self.base_path = base_path
        self.dashboard_path = os.path.abspath(dashboard_path)
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pnl_log_path(self, strategy: str) -> str:
        """Relative path (from base_path) of the per-strategy P&L log."""
        return f"{PNL_LOG_DIR}/{strategy}_pnl.jsonl"

    def _stats_path(self, mode: str) -> str:
        """Absolute path of the dashboard stats file for the given mode."""
        filename = PAPER_STATS_FILE if mode == "paper" else LIVE_STATS_FILE
        return os.path.join(self.dashboard_path, filename)

    def _read_stats(self, mode: str) -> dict:
        """Read the dashboard stats file.  Returns empty structure if absent."""
        path = self._stats_path(mode)
        if not os.path.exists(path):
            return {"last_updated": None, "strategies": {}}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_stats(self, mode: str, data: dict) -> None:
        """Atomic write of the dashboard stats file."""
        path = self._stats_path(mode)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_trade(
        self,
        strategy: str,
        pnl: float,
        mode: str = "paper",
        trade_id: str = None,
        market_id: str = None,
    ) -> None:
        """Append a resolved trade P&L to the per-strategy log.

        Called by the orchestrator (or execution engine) after a market
        resolves and the final P&L for the position is known.

        Args:
            strategy:  Strategy name (e.g. "POLY_ARB_SCANNER").
            pnl:       Resolved trade P&L in EUR (positive = win, negative = loss).
            mode:      "paper" or "live".
            trade_id:  Optional trade identifier for traceability.
            market_id: Optional market identifier for traceability.
        """
        record = {
            "strategy": strategy,
            "pnl": pnl,
            "mode": mode,
            "trade_id": trade_id,
            "market_id": market_id,
            "timestamp": _now_utc(),
        }
        self.store.append_jsonl(self._pnl_log_path(strategy), record)

    def compute_metrics(self, strategy: str) -> dict:
        """Compute six performance metrics from the per-strategy P&L log.

        Pure method — no side effects, no bus events.

        Args:
            strategy: Strategy name.

        Returns:
            Dict with: total_trades, win_rate, total_pnl, profit_factor,
            sharpe_ratio, max_drawdown_eur.
        """
        records = self.store.read_jsonl(self._pnl_log_path(strategy))
        pnl_series = [r["pnl"] for r in records]
        n = len(pnl_series)

        if n == 0:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_eur": 0.0,
            }

        wins = sum(1 for p in pnl_series if p > 0)
        total_pnl = sum(pnl_series)
        gross_profit = sum(p for p in pnl_series if p > 0)
        gross_loss = sum(abs(p) for p in pnl_series if p < 0)

        return {
            "total_trades": n,
            "win_rate": round(wins / n, 6),
            "total_pnl": round(total_pnl, 6),
            "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else 0.0,
            "sharpe_ratio": round(_compute_sharpe(pnl_series), 6),
            "max_drawdown_eur": round(_compute_max_drawdown(pnl_series), 6),
        }

    def update_stats(self, strategy: str, mode: str = "paper") -> dict:
        """Compute metrics, write to dashboard stats file, check milestones.

        Reads the current stats to detect milestone crossings (a milestone
        fires only the first time total_trades crosses that threshold).
        Publishes eval:milestone on the bus and to the audit log.

        Args:
            strategy: Strategy name.
            mode:     "paper" or "live".

        Returns:
            Dict with: strategy, mode, metrics.
        """
        metrics = self.compute_metrics(strategy)
        now = _now_utc()

        # Read previous stats to detect milestone crossings
        stats = self._read_stats(mode)
        prev_entry = stats.get("strategies", {}).get(strategy, {})
        prev_total = prev_entry.get("total_trades", 0)
        new_total = metrics["total_trades"]

        # Write updated stats
        stats.setdefault("strategies", {})[strategy] = {
            **metrics,
            "last_updated": now,
        }
        stats["last_updated"] = now
        self._write_stats(mode, stats)

        # Check milestones — fire only on first crossing
        for milestone in MILESTONE_COUNTS:
            if prev_total < milestone <= new_total:
                payload = {
                    "strategy": strategy,
                    "mode": mode,
                    "milestone": milestone,
                    "metrics": metrics,
                }
                self.bus.publish("eval:milestone", CONSUMER_ID, payload)
                self.audit.log_event("eval:milestone", CONSUMER_ID, payload)

        return {
            "strategy": strategy,
            "mode": mode,
            "metrics": metrics,
        }

    def get_stats(self, mode: str = "paper") -> dict:
        """Return the current dashboard stats for all strategies.

        Args:
            mode: "paper" or "live".

        Returns:
            Full stats dict with strategies map.
        """
        return self._read_stats(mode)

    def run_once(self, strategies: list, mode: str = "paper") -> list:
        """Batch update: compute and persist metrics for every listed strategy.

        Called nightly by the orchestrator (03:15 UTC) and at milestones.

        Args:
            strategies: List of strategy names to refresh.
            mode:       "paper" or "live".

        Returns:
            List of update_stats result dicts, one per strategy.
        """
        results = []
        for strategy in strategies:
            result = self.update_stats(strategy, mode)
            results.append(result)
        return results
