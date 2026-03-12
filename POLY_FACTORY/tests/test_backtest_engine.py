"""
Tests for POLY_BACKTEST_ENGINE (POLY-013).
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from evaluation.poly_backtest_engine import (
    MAX_CONCURRENT_BACKTESTS,
    TRADABILITY_MALUS,
    PolyBacktestEngine,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_tick(i, yes_price, market_id="0xabc", base_ts=None):
    """Create a single tick at minute offset i."""
    if base_ts is None:
        base_ts = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    ts = (base_ts + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
    no_price = round(1.0 - yes_price, 6)
    return {
        "timestamp": ts,
        "market_id": market_id,
        "yes_price": yes_price,
        "no_price": no_price,
        "volume_24h": 1000.0,
    }


def _rising_ticks(n=20, start=0.30, end=0.70):
    """yes_price rises linearly from start to end over n ticks."""
    ticks = []
    for i in range(n):
        price = start + (end - start) * i / max(n - 1, 1)
        ticks.append(_make_tick(i, round(price, 6)))
    return ticks


def _falling_ticks(n=20, start=0.70, end=0.30):
    """yes_price falls linearly from start to end over n ticks."""
    ticks = []
    for i in range(n):
        price = start + (end - start) * i / max(n - 1, 1)
        ticks.append(_make_tick(i, round(price, 6)))
    return ticks


def _flat_ticks(n=20, price=0.50):
    """Constant yes_price."""
    return [_make_tick(i, price) for i in range(n)]


_buy_triggered = False  # module-level state reset per test below


def _buy_at_start_sell_at_end(tick):
    """BUY_YES on the very first call, SELL on the last (determined by price extremes)."""
    # Simple: BUY_YES if no position signal needed — callers manage externally.
    # For simplicity: always return BUY_YES (engine ignores if position already open).
    return {"action": "BUY_YES", "size": 10.0}


def _always_hold(tick):
    return {"action": "HOLD", "size": 0.0}


def _buy_then_sell_factory():
    """Returns a signal_fn that buys on tick 0, sells on tick 1, holds thereafter."""
    state = {"bought": False, "sold": False}

    def fn(tick):
        if not state["bought"]:
            state["bought"] = True
            return {"action": "BUY_YES", "size": 10.0}
        if not state["sold"]:
            state["sold"] = True
            return {"action": "SELL", "size": 0.0}
        return {"action": "HOLD", "size": 0.0}

    return fn


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def engine(tmp_path):
    return PolyBacktestEngine(base_path=str(tmp_path))


# ---------------------------------------------------------------------------
# Data validation tests
# ---------------------------------------------------------------------------

def test_valid_ticks_passes_validation(engine):
    ticks = _rising_ticks(n=10)
    result = engine._validate_ticks(ticks)
    assert result["valid"] is True
    assert result["issues"] == []


def test_too_few_ticks_fails(engine):
    result = engine._validate_ticks([_make_tick(0, 0.5)])
    assert result["valid"] is False
    assert any("Too few" in issue for issue in result["issues"])


def test_gap_over_1h_fails(engine):
    base = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    tick0 = {
        "timestamp": base.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market_id": "0xabc",
        "yes_price": 0.5,
        "no_price": 0.5,
        "volume_24h": 100.0,
    }
    tick1 = {
        "timestamp": (base + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market_id": "0xabc",
        "yes_price": 0.5,
        "no_price": 0.5,
        "volume_24h": 100.0,
    }
    result = engine._validate_ticks([tick0, tick1])
    assert result["valid"] is False
    assert any("gap" in issue.lower() for issue in result["issues"])


def test_aberrant_price_fails(engine):
    ticks = _rising_ticks(n=5)
    ticks[2]["yes_price"] = 1.5  # invalid
    result = engine._validate_ticks(ticks)
    assert result["valid"] is False
    assert any("yes_price" in issue for issue in result["issues"])


# ---------------------------------------------------------------------------
# P&L / metric tests
# ---------------------------------------------------------------------------

def test_winning_trade_positive_pnl(engine):
    # BUY_YES at 0.30, sell at 0.70 → PnL = 0.40 * 10
    ticks = _rising_ticks(n=20, start=0.30, end=0.70)
    bought = [False]

    def signal(tick):
        if not bought[0]:
            bought[0] = True
            return {"action": "BUY_YES", "size": 10.0}
        return {"action": "HOLD", "size": 0.0}

    trades = engine._simulate_trades(ticks, signal)
    assert len(trades) == 1
    assert trades[0]["pnl"] > 0
    assert abs(trades[0]["pnl"] - (0.70 - 0.30) * 10.0) < 0.01


def test_losing_trade_negative_pnl(engine):
    # BUY_YES at 0.70, sell at 0.30 → PnL = -0.40 * 10
    ticks = _falling_ticks(n=20, start=0.70, end=0.30)
    bought = [False]

    def signal(tick):
        if not bought[0]:
            bought[0] = True
            return {"action": "BUY_YES", "size": 10.0}
        return {"action": "HOLD", "size": 0.0}

    trades = engine._simulate_trades(ticks, signal)
    assert len(trades) == 1
    assert trades[0]["pnl"] < 0


def test_buy_no_positive_when_price_falls(engine):
    # BUY_NO when yes=0.70 (no=0.30), then yes falls to 0.30 → positive
    ticks = _falling_ticks(n=20, start=0.70, end=0.30)
    bought = [False]
    sold = [False]

    def signal(tick):
        if not bought[0]:
            bought[0] = True
            return {"action": "BUY_NO", "size": 10.0}
        if not sold[0] and tick["yes_price"] < 0.35:
            sold[0] = True
            return {"action": "SELL", "size": 0.0}
        return {"action": "HOLD", "size": 0.0}

    trades = engine._simulate_trades(ticks, signal)
    assert len(trades) == 1
    assert trades[0]["pnl"] > 0


def test_win_rate_correct(engine):
    # 3 trades: 2 winners, 1 loser
    trades = [
        {"side": "YES", "entry_price": 0.3, "exit_price": 0.7, "size": 10, "pnl": 4.0, "entry_ts": "", "exit_ts": ""},
        {"side": "YES", "entry_price": 0.3, "exit_price": 0.7, "size": 10, "pnl": 4.0, "entry_ts": "", "exit_ts": ""},
        {"side": "YES", "entry_price": 0.7, "exit_price": 0.3, "size": 10, "pnl": -4.0, "entry_ts": "", "exit_ts": ""},
    ]
    metrics = engine._compute_metrics(trades, 1000.0)
    assert abs(metrics["win_rate"] - 2 / 3) < 1e-9


def test_profit_factor_correct(engine):
    # gross_profit=8, gross_loss=4 → ratio=2.0
    trades = [
        {"pnl": 4.0, "side": "YES", "entry_price": 0.3, "exit_price": 0.7, "size": 10, "entry_ts": "", "exit_ts": ""},
        {"pnl": 4.0, "side": "YES", "entry_price": 0.3, "exit_price": 0.7, "size": 10, "entry_ts": "", "exit_ts": ""},
        {"pnl": -4.0, "side": "YES", "entry_price": 0.7, "exit_price": 0.3, "size": 10, "entry_ts": "", "exit_ts": ""},
    ]
    metrics = engine._compute_metrics(trades, 1000.0)
    assert abs(metrics["profit_factor"] - 2.0) < 1e-9


def test_max_drawdown_negative_or_zero(engine):
    # Any non-empty series should return ≤ 0
    pnl = [10.0, -20.0, 5.0, -3.0]
    dd = engine._compute_max_drawdown(pnl)
    assert dd <= 0


def test_sharpe_zero_with_fewer_than_2_trades(engine):
    assert engine._compute_sharpe([]) == 0.0
    assert engine._compute_sharpe([5.0]) == 0.0


def test_no_trades_metrics(engine):
    metrics = engine._compute_metrics([], 1000.0)
    assert metrics["total_trades"] == 0
    assert metrics["win_rate"] == 0.0
    assert metrics["total_pnl"] == 0.0
    assert metrics["total_return_pct"] == 0.0
    assert metrics["max_drawdown_pct"] == 0.0
    assert metrics["profit_factor"] is None
    assert metrics["sharpe_ratio"] == 0.0


def test_open_position_closed_at_end(engine):
    """BUY without SELL → position closed at last tick price."""
    ticks = _rising_ticks(n=10, start=0.30, end=0.70)
    bought = [False]

    def signal(tick):
        if not bought[0]:
            bought[0] = True
            return {"action": "BUY_YES", "size": 5.0}
        return {"action": "HOLD", "size": 0.0}

    trades = engine._simulate_trades(ticks, signal)
    assert len(trades) == 1
    assert trades[0]["exit_ts"] == ticks[-1]["timestamp"]
    assert trades[0]["pnl"] > 0  # price went up


# ---------------------------------------------------------------------------
# Concurrency / limit tests
# ---------------------------------------------------------------------------

def test_max_concurrent_raises_on_4th(engine):
    engine._active_backtests = MAX_CONCURRENT_BACKTESTS
    with pytest.raises(RuntimeError, match="Max concurrent backtests"):
        engine.run("POLY_TEST", _flat_ticks(), _always_hold)
    # Reset so teardown is clean
    engine._active_backtests = 0


def test_counter_released_on_completion(engine):
    engine.run("POLY_TEST", _rising_ticks(), _always_hold)
    assert engine._active_backtests == 0


def test_counter_released_on_error(engine):
    def bad_signal(tick):
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        engine.run("POLY_TEST", _rising_ticks(), bad_signal)
    assert engine._active_backtests == 0


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def test_run_saves_result_file(engine, tmp_path):
    engine.run("POLY_ARB_SCANNER", _rising_ticks(), _always_hold)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    expected = tmp_path / "research" / "backtest_results" / f"POLY_ARB_SCANNER_{date_str}.json"
    assert expected.exists()


def test_run_result_has_all_fields(engine):
    result = engine.run("POLY_ARB_SCANNER", _rising_ticks(), _always_hold)
    for field in ("backtest_id", "strategy_id", "run_date", "market_ids",
                  "n_ticks", "n_trades", "metrics", "data_validation",
                  "tradability_malus", "doctrine_warning"):
        assert field in result, f"Missing field: {field}"


def test_doctrine_warning_in_output(engine):
    result = engine.run("POLY_ARB_SCANNER", _rising_ticks(), _always_hold)
    assert result["doctrine_warning"] != ""
    assert "screening" in result["doctrine_warning"].lower()


def test_tradability_malus_in_output(engine):
    result = engine.run("POLY_ARB_SCANNER", _rising_ticks(), _always_hold)
    assert result["tradability_malus"] == TRADABILITY_MALUS
    assert result["tradability_malus"] == -15


def test_audit_log_entries(engine, tmp_path):
    engine.run("POLY_ARB_SCANNER", _rising_ticks(), _always_hold)
    from core.poly_audit_log import PolyAuditLog
    audit = PolyAuditLog(base_path=str(tmp_path))
    events = audit.read_events()
    topics = [e["topic"] for e in events]
    assert "evaluation:backtest_started" in topics
    assert "evaluation:backtest_completed" in topics
