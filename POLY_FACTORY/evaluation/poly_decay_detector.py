"""
POLY_DECAY_DETECTOR — Rolling 7-day vs 30-day strategy decay detection.

Compares recent (7-day) strategy performance against the 30-day baseline
on 4 key metrics and assigns one of 4 severity levels.

4 monitored axes with per-axis decline thresholds:
  win_rate      — 2pp drop
  sharpe_ratio  — 0.10 drop
  profit_factor — 0.10 drop
  avg_pnl       — any drop in average P&L per trade

4 severity levels (from declining axis count + win_rate special rule):
  HEALTHY  — 0 axes declining and WR drop < 7pp — no action
  WARNING  — 1 axis declining OR win_rate drops ≥ 7pp — log only
  SERIOUS  — 2 axes declining — account → "paused"
  CRITICAL — 3+ axes declining — account → "paused", urgent alert

Reads  : {base_path}/trading/positions_by_strategy/{strategy}_pnl.jsonl
Writes : state/evaluation/decay_alerts.json
Emits  : eval:decay_alert (bus + audit)
Actions: SERIOUS/CRITICAL → PolyStrategyAccount.update_status("paused")

Run nightly at 03:30 UTC by the orchestrator.
"""

import math
from datetime import datetime, timezone, timedelta

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_strategy_account import PolyStrategyAccount


CONSUMER_ID = "POLY_DECAY_DETECTOR"

ALERTS_FILE  = "evaluation/decay_alerts.json"
PNL_LOG_DIR  = "trading/positions_by_strategy"

WINDOW_SHORT_DAYS = 7
WINDOW_LONG_DAYS  = 30

# Per-axis decline threshold: metric is "declining" if short < long - threshold
DECLINE_THRESHOLDS = {
    "win_rate":      0.02,   # 2 percentage-point drop
    "sharpe_ratio":  0.10,   # 0.10 drop in Sharpe
    "profit_factor": 0.10,   # 0.10 drop in profit factor
    "avg_pnl":       0.0,    # any drop in average P&L per trade
}

# Win-rate special rule: ≥ 7pp drop → at least WARNING regardless of axis count
WR_WARNING_DROP = 0.07

SEVERITY_HEALTHY  = "HEALTHY"
SEVERITY_WARNING  = "WARNING"
SEVERITY_SERIOUS  = "SERIOUS"
SEVERITY_CRITICAL = "CRITICAL"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts_str: str) -> datetime:
    return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _compute_metrics_from_series(pnl_series: list) -> dict:
    """Compute win_rate, sharpe_ratio, profit_factor, avg_pnl from a P&L list.

    Pure function — no I/O.
    """
    n = len(pnl_series)
    if n == 0:
        return {
            "total_trades":  0,
            "win_rate":      0.0,
            "sharpe_ratio":  0.0,
            "profit_factor": 0.0,
            "avg_pnl":       0.0,
        }

    wins         = sum(1 for p in pnl_series if p > 0)
    total_pnl    = sum(pnl_series)
    gross_profit = sum(p for p in pnl_series if p > 0)
    gross_loss   = sum(abs(p) for p in pnl_series if p < 0)

    # Sharpe: mean / std * sqrt(n)
    mean = total_pnl / n
    if n >= 2:
        variance = sum((p - mean) ** 2 for p in pnl_series) / (n - 1)
        std = math.sqrt(variance)
        sharpe = (mean / std) * math.sqrt(n) if std > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "total_trades":  n,
        "win_rate":      round(wins / n, 6),
        "sharpe_ratio":  round(sharpe, 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else 0.0,
        "avg_pnl":       round(total_pnl / n, 6),
    }


class PolyDecayDetector:
    """Rolling 7-day vs 30-day decay detection with 4 severity levels."""

    def __init__(self, base_path="state"):
        self.base_path = base_path
        self.store = PolyDataStore(base_path=base_path)
        self.bus   = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)

    # ------------------------------------------------------------------
    # Rolling window helpers
    # ------------------------------------------------------------------

    def compute_rolling_metrics(self, strategy: str) -> dict:
        """Compute metrics for the short (7d) and long (30d) rolling windows.

        Args:
            strategy: Strategy name.

        Returns:
            Dict with keys "short" and "long", each containing a metrics dict
            from _compute_metrics_from_series().
        """
        records = self.store.read_jsonl(f"{PNL_LOG_DIR}/{strategy}_pnl.jsonl")
        now          = datetime.now(timezone.utc)
        cutoff_short = now - timedelta(days=WINDOW_SHORT_DAYS)
        cutoff_long  = now - timedelta(days=WINDOW_LONG_DAYS)

        short_series = [
            r["pnl"] for r in records
            if _parse_ts(r["timestamp"]) >= cutoff_short
        ]
        long_series = [
            r["pnl"] for r in records
            if _parse_ts(r["timestamp"]) >= cutoff_long
        ]

        return {
            "short": _compute_metrics_from_series(short_series),
            "long":  _compute_metrics_from_series(long_series),
        }

    def _find_declining_axes(self, short: dict, long: dict) -> list:
        """Return list of axis names that are declining in the short window.

        An axis is declining when: short_value < long_value - threshold.

        Args:
            short: Metrics for the 7-day window.
            long:  Metrics for the 30-day window.

        Returns:
            List of axis names (subset of DECLINE_THRESHOLDS keys).
        """
        declining = []
        for axis, threshold in DECLINE_THRESHOLDS.items():
            if short.get(axis, 0.0) < long.get(axis, 0.0) - threshold:
                declining.append(axis)
        return declining

    def _compute_severity(
        self, declining_axes: list, short: dict, long: dict
    ) -> str:
        """Map declining axis count (and WR special rule) to a severity string.

        Rules (evaluated in priority order):
          1. declining_count >= 3  → CRITICAL
          2. declining_count == 2  → SERIOUS
          3. WR drop >= 7pp OR declining_count == 1  → WARNING
          4. Otherwise → HEALTHY

        Args:
            declining_axes: Output of _find_declining_axes().
            short: 7-day metrics.
            long:  30-day metrics.

        Returns:
            One of: HEALTHY, WARNING, SERIOUS, CRITICAL.
        """
        n = len(declining_axes)
        wr_drop = long.get("win_rate", 0.0) - short.get("win_rate", 0.0)

        if n >= 3:
            return SEVERITY_CRITICAL
        if n == 2:
            return SEVERITY_SERIOUS
        if wr_drop >= WR_WARNING_DROP or n == 1:
            return SEVERITY_WARNING
        return SEVERITY_HEALTHY

    # ------------------------------------------------------------------
    # Detect + persist + act
    # ------------------------------------------------------------------

    def detect(self, strategy: str, account_id: str) -> dict:
        """Full detection pipeline for one strategy.

        1. Computes 7-day and 30-day rolling metrics.
        2. Finds declining axes.
        3. Determines severity.
        4. Persists to decay_alerts.json.
        5. Publishes eval:decay_alert on bus + audit log.
        6. If SERIOUS or CRITICAL: pauses the account.

        Args:
            strategy:   Strategy name (e.g. "POLY_ARB_SCANNER").
            account_id: Full account ID (e.g. "ACC_POLY_ARB_SCANNER").

        Returns:
            Dict with: strategy, account_id, severity, declining_axes,
            short_metrics, long_metrics, action, detected_at.
        """
        windows        = self.compute_rolling_metrics(strategy)
        short          = windows["short"]
        long_m         = windows["long"]
        declining_axes = self._find_declining_axes(short, long_m)
        severity       = self._compute_severity(declining_axes, short, long_m)
        now            = _now_utc()

        if severity in (SEVERITY_SERIOUS, SEVERITY_CRITICAL):
            action = "pause_account"
        elif severity == SEVERITY_WARNING:
            action = "log_only"
        else:
            action = "none"

        result = {
            "strategy":       strategy,
            "account_id":     account_id,
            "severity":       severity,
            "declining_axes": declining_axes,
            "short_metrics":  short,
            "long_metrics":   long_m,
            "action":         action,
            "detected_at":    now,
        }

        # Persist to decay_alerts.json
        all_alerts = self.store.read_json(ALERTS_FILE) or {}
        all_alerts[strategy] = result
        self.store.write_json(ALERTS_FILE, all_alerts)

        # Bus + audit
        payload = {
            "strategy":       strategy,
            "account_id":     account_id,
            "severity":       severity,
            "declining_axes": declining_axes,
            "action":         action,
        }
        self.bus.publish("eval:decay_alert", CONSUMER_ID, payload)
        self.audit.log_event("eval:decay_alert", CONSUMER_ID, payload)

        # Account action: pause on SERIOUS or CRITICAL
        if action == "pause_account":
            try:
                account = PolyStrategyAccount.load(account_id, self.base_path)
                if account.data.get("status") not in ("paused", "stopped"):
                    account.update_status("paused")
            except FileNotFoundError:
                pass  # No account file — skip silently

        return result

    # ------------------------------------------------------------------
    # Batch + accessors
    # ------------------------------------------------------------------

    def run_once(self, strategies: list) -> list:
        """Batch detection for all listed strategies.

        Args:
            strategies: List of strategy names.

        Returns:
            List of detect() result dicts, one per strategy.
        """
        results = []
        for strategy in strategies:
            account_id = f"ACC_{strategy}"
            result = self.detect(strategy, account_id)
            results.append(result)
        return results

    def get_alerts(self) -> dict:
        """Return the full decay_alerts.json dict."""
        return self.store.read_json(ALERTS_FILE) or {}
