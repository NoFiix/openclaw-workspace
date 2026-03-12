"""
POLY_BACKTEST_ENGINE — Historical market replay engine for POLY_FACTORY.

Quick strategy screening tool. Processes tick-by-tick price data with a pluggable
signal function, simulates trade P&L, and computes financial metrics.

DOCTRINE: Backtest alone is NEVER sufficient for live promotion.
Required: backtest + paper trading (≥50 trades, ≥14 days) + confirmed tradability.
"""

import math
import threading
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore


RESULTS_DIR = "research/backtest_results"
MAX_CONCURRENT_BACKTESTS = 3
MAX_GAP_SECONDS = 3600  # 1 hour
TRADABILITY_MALUS = -15
DOCTRINE_WARNING = (
    "Backtest is a quick screening tool only. A positive result is NOT sufficient "
    "for live promotion. Required: backtest + paper trading (≥50 trades, ≥14 days) "
    "+ confirmed tradability."
)


class PolyBacktestEngine:
    """Historical market replay engine with pluggable signal function."""

    def __init__(self, base_path="state"):
        self.store = PolyDataStore(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self._active_backtests = 0
        self._lock = threading.Lock()
        self._id_counter = 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_backtest_id(self) -> str:
        """Thread-safe backtest ID: BT_{YYYYMMDD}_{counter:04d}."""
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        with self._lock:
            self._id_counter += 1
            counter = self._id_counter
        return f"BT_{date_str}_{counter:04d}"

    def _validate_ticks(self, ticks) -> dict:
        """Validate tick list. Returns {"valid": bool, "issues": list}."""
        issues = []

        if len(ticks) < 2:
            issues.append("Too few ticks: need at least 2")
            return {"valid": False, "issues": issues}

        prev_ts = None
        for i, tick in enumerate(ticks):
            # Parse timestamp
            try:
                ts_str = tick["timestamp"]
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (KeyError, ValueError) as e:
                issues.append(f"Tick {i}: invalid timestamp — {e}")
                continue

            # Ascending order
            if prev_ts is not None:
                if ts < prev_ts:
                    issues.append(f"Tick {i}: timestamp not ascending")
                else:
                    gap = (ts - prev_ts).total_seconds()
                    if gap > MAX_GAP_SECONDS:
                        issues.append(
                            f"Tick {i}: gap of {gap:.0f}s exceeds {MAX_GAP_SECONDS}s"
                        )
            prev_ts = ts

            # Price bounds
            yes_price = tick.get("yes_price")
            no_price = tick.get("no_price")
            if yes_price is None or not (0 < yes_price < 1):
                issues.append(f"Tick {i}: yes_price={yes_price} not in (0, 1)")
            if no_price is None or not (0 < no_price < 1):
                issues.append(f"Tick {i}: no_price={no_price} not in (0, 1)")

        return {"valid": len(issues) == 0, "issues": issues}

    def _simulate_trades(self, ticks, signal_fn) -> list:
        """Replay ticks through signal_fn; return list of closed trade dicts."""
        trades = []
        position = None  # {"side": "YES"|"NO", "entry_price": float, "size": float, "entry_ts": str}

        for tick in ticks:
            signal = signal_fn(tick)
            action = signal.get("action", "HOLD")
            size = float(signal.get("size", 0.0))

            if action in ("BUY_YES", "BUY_NO") and position is None:
                side = "YES" if action == "BUY_YES" else "NO"
                entry_price = tick["yes_price"] if side == "YES" else tick["no_price"]
                position = {
                    "side": side,
                    "entry_price": entry_price,
                    "size": size,
                    "entry_ts": tick["timestamp"],
                }

            elif action == "SELL" and position is not None:
                trade = self._close_position(position, tick)
                trades.append(trade)
                position = None

        # Close any open position at final tick price
        if position is not None:
            trade = self._close_position(position, ticks[-1])
            trades.append(trade)

        return trades

    def _close_position(self, position, tick) -> dict:
        """Close a position at the given tick, compute P&L."""
        side = position["side"]
        entry_price = position["entry_price"]
        size = position["size"]

        if side == "YES":
            exit_price = tick["yes_price"]
            pnl = (exit_price - entry_price) * size
        else:
            # BUY_NO: entry was at no_price = 1 - yes_price_entry
            # PnL = -(yes_exit - yes_entry) * size
            yes_exit = tick["yes_price"]
            yes_entry = 1.0 - entry_price
            pnl = -(yes_exit - yes_entry) * size
            exit_price = tick["no_price"]

        return {
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "size": size,
            "pnl": pnl,
            "entry_ts": position["entry_ts"],
            "exit_ts": tick["timestamp"],
        }

    def _compute_metrics(self, trades, initial_capital) -> dict:
        """Compute the 7 financial metrics from closed trades."""
        n = len(trades)

        if n == 0:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "total_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "profit_factor": None,
                "sharpe_ratio": 0.0,
            }

        pnl_series = [t["pnl"] for t in trades]
        total_pnl = sum(pnl_series)
        wins = sum(1 for p in pnl_series if p > 0)
        gross_profit = sum(p for p in pnl_series if p > 0)
        gross_loss = sum(abs(p) for p in pnl_series if p < 0)

        return {
            "total_trades": n,
            "win_rate": wins / n,
            "total_pnl": total_pnl,
            "total_return_pct": (total_pnl / initial_capital) * 100.0,
            "max_drawdown_pct": self._compute_max_drawdown(pnl_series),
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else 0.0,
            "sharpe_ratio": self._compute_sharpe(pnl_series),
        }

    def _compute_max_drawdown(self, pnl_series) -> float:
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
            drawdown = equity - peak
            if drawdown < max_dd:
                max_dd = drawdown

        return max_dd

    def _compute_sharpe(self, pnl_series) -> float:
        """mean(PnL) / std(PnL) * sqrt(n). Returns 0.0 if n < 2 or std == 0."""
        n = len(pnl_series)
        if n < 2:
            return 0.0

        mean = sum(pnl_series) / n
        variance = sum((p - mean) ** 2 for p in pnl_series) / (n - 1)
        std = math.sqrt(variance)

        if std == 0:
            return 0.0

        return (mean / std) * math.sqrt(n)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, strategy_id: str, ticks: list, signal_fn, initial_capital: float = 1000.0) -> dict:
        """Run a backtest for a given strategy and tick sequence.

        Args:
            strategy_id: Strategy identifier (e.g. "POLY_ARB_SCANNER").
            ticks: List of tick dicts with timestamp, market_id, yes_price, no_price, volume_24h.
            signal_fn: Callable(tick) -> {"action": str, "size": float}.
            initial_capital: Capital baseline for return % calculation (default 1000.0).

        Returns:
            Result dict with metrics, validation, and doctrine warning.

        Raises:
            RuntimeError: If MAX_CONCURRENT_BACKTESTS is already reached.
        """
        with self._lock:
            if self._active_backtests >= MAX_CONCURRENT_BACKTESTS:
                raise RuntimeError(
                    f"Max concurrent backtests ({MAX_CONCURRENT_BACKTESTS}) reached"
                )
            self._active_backtests += 1

        backtest_id = self._generate_backtest_id()
        run_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        date_suffix = datetime.now(timezone.utc).strftime("%Y%m%d")

        try:
            self.audit.log_event(
                topic="evaluation:backtest_started",
                producer="POLY_BACKTEST_ENGINE",
                payload={"backtest_id": backtest_id, "strategy_id": strategy_id, "n_ticks": len(ticks)},
            )

            data_validation = self._validate_ticks(ticks)

            if data_validation["valid"]:
                trades = self._simulate_trades(ticks, signal_fn)
                metrics = self._compute_metrics(trades, initial_capital)
            else:
                trades = []
                metrics = self._compute_metrics([], initial_capital)

            market_ids = list({t.get("market_id", "") for t in ticks if t.get("market_id")})

            result = {
                "backtest_id": backtest_id,
                "strategy_id": strategy_id,
                "run_date": run_date,
                "market_ids": market_ids,
                "n_ticks": len(ticks),
                "n_trades": metrics["total_trades"],
                "metrics": metrics,
                "data_validation": data_validation,
                "tradability_malus": TRADABILITY_MALUS,
                "doctrine_warning": DOCTRINE_WARNING,
            }

            output_path = f"{RESULTS_DIR}/{strategy_id}_{date_suffix}.json"
            self.store.write_json(output_path, result)

            self.audit.log_event(
                topic="evaluation:backtest_completed",
                producer="POLY_BACKTEST_ENGINE",
                payload={
                    "backtest_id": backtest_id,
                    "strategy_id": strategy_id,
                    "n_trades": metrics["total_trades"],
                    "total_pnl": metrics["total_pnl"],
                },
            )

            return result

        finally:
            with self._lock:
                self._active_backtests -= 1
