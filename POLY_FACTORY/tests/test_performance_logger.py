"""
Tests for POLY_PERFORMANCE_LOGGER (POLY-025).

Key acceptance criteria from ticket:
- 50 trades simulés → WR/Sharpe/PF calculés, milestone 50 émis
"""

import pytest
import math
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from evaluation.poly_performance_logger import (
    PolyPerformanceLogger,
    CONSUMER_ID,
    MILESTONE_COUNTS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def logger(tmp_path):
    dashboard = tmp_path / "dashboard-data"
    return PolyPerformanceLogger(
        base_path=str(tmp_path),
        dashboard_path=str(dashboard),
    )


STRATEGY = "POLY_ARB_SCANNER"


def _log_n_trades(logger, n, win_pnl=10.0, loss_pnl=-5.0, win_rate=0.6, strategy=STRATEGY, mode="paper"):
    """Log n trades with the given win rate and P&L amounts."""
    wins = round(n * win_rate)
    for i in range(n):
        pnl = win_pnl if i < wins else loss_pnl
        logger.log_trade(strategy, pnl, mode=mode, trade_id=f"TRD_{i:04d}")


# ---------------------------------------------------------------------------
# Ticket acceptance criteria
# ---------------------------------------------------------------------------

def test_50_trades_wr_sharpe_pf_computed(logger):
    """50 trades simulés → WR/Sharpe/PF calculés."""
    _log_n_trades(logger, 50, win_pnl=10.0, loss_pnl=-5.0, win_rate=0.6)
    metrics = logger.compute_metrics(STRATEGY)
    assert metrics["total_trades"] == 50
    assert metrics["win_rate"] > 0.0
    assert metrics["sharpe_ratio"] != 0.0
    assert metrics["profit_factor"] > 0.0


def test_50_trades_milestone_emitted(logger):
    """50 trades → eval:milestone event published on bus."""
    store = PolyDataStore(base_path=logger.base_path)
    _log_n_trades(logger, 50)
    logger.update_stats(STRATEGY, mode="paper")
    events = store.read_jsonl("bus/pending_events.jsonl")
    milestone_events = [e for e in events if e.get("topic") == "eval:milestone"]
    assert len(milestone_events) == 1
    assert milestone_events[0]["payload"]["milestone"] == 50


# ---------------------------------------------------------------------------
# log_trade
# ---------------------------------------------------------------------------

def test_log_trade_creates_pnl_log(logger):
    logger.log_trade(STRATEGY, 10.0)
    store = PolyDataStore(base_path=logger.base_path)
    records = store.read_jsonl(f"trading/positions_by_strategy/{STRATEGY}_pnl.jsonl")
    assert len(records) == 1


def test_log_trade_stores_pnl_value(logger):
    logger.log_trade(STRATEGY, -7.5)
    store = PolyDataStore(base_path=logger.base_path)
    records = store.read_jsonl(f"trading/positions_by_strategy/{STRATEGY}_pnl.jsonl")
    assert records[0]["pnl"] == -7.5


def test_log_trade_stores_strategy(logger):
    logger.log_trade(STRATEGY, 5.0)
    store = PolyDataStore(base_path=logger.base_path)
    records = store.read_jsonl(f"trading/positions_by_strategy/{STRATEGY}_pnl.jsonl")
    assert records[0]["strategy"] == STRATEGY


def test_log_trade_stores_trade_id(logger):
    logger.log_trade(STRATEGY, 5.0, trade_id="TRD_0042")
    store = PolyDataStore(base_path=logger.base_path)
    records = store.read_jsonl(f"trading/positions_by_strategy/{STRATEGY}_pnl.jsonl")
    assert records[0]["trade_id"] == "TRD_0042"


def test_log_multiple_trades_appends(logger):
    for pnl in [5.0, -3.0, 8.0]:
        logger.log_trade(STRATEGY, pnl)
    store = PolyDataStore(base_path=logger.base_path)
    records = store.read_jsonl(f"trading/positions_by_strategy/{STRATEGY}_pnl.jsonl")
    assert len(records) == 3


# ---------------------------------------------------------------------------
# compute_metrics — zero trades
# ---------------------------------------------------------------------------

def test_compute_metrics_no_trades_returns_zeros(logger):
    metrics = logger.compute_metrics(STRATEGY)
    assert metrics["total_trades"] == 0
    assert metrics["win_rate"] == 0.0
    assert metrics["total_pnl"] == 0.0
    assert metrics["profit_factor"] == 0.0
    assert metrics["sharpe_ratio"] == 0.0
    assert metrics["max_drawdown_eur"] == 0.0


def test_compute_metrics_has_all_fields(logger):
    logger.log_trade(STRATEGY, 10.0)
    metrics = logger.compute_metrics(STRATEGY)
    for field in ("total_trades", "win_rate", "total_pnl", "profit_factor",
                  "sharpe_ratio", "max_drawdown_eur"):
        assert field in metrics


# ---------------------------------------------------------------------------
# compute_metrics — win_rate
# ---------------------------------------------------------------------------

def test_win_rate_all_wins(logger):
    for _ in range(10):
        logger.log_trade(STRATEGY, 5.0)
    metrics = logger.compute_metrics(STRATEGY)
    assert metrics["win_rate"] == 1.0


def test_win_rate_all_losses(logger):
    for _ in range(10):
        logger.log_trade(STRATEGY, -5.0)
    metrics = logger.compute_metrics(STRATEGY)
    assert metrics["win_rate"] == 0.0


def test_win_rate_mixed(logger):
    # 3 wins, 2 losses → 60%
    for pnl in [10.0, 10.0, 10.0, -5.0, -5.0]:
        logger.log_trade(STRATEGY, pnl)
    metrics = logger.compute_metrics(STRATEGY)
    assert abs(metrics["win_rate"] - 0.6) < 1e-4


# ---------------------------------------------------------------------------
# compute_metrics — profit_factor
# ---------------------------------------------------------------------------

def test_profit_factor_computed(logger):
    # gross_profit=30, gross_loss=10 → PF=3.0
    for pnl in [10.0, 10.0, 10.0, -5.0, -5.0]:
        logger.log_trade(STRATEGY, pnl)
    metrics = logger.compute_metrics(STRATEGY)
    assert abs(metrics["profit_factor"] - 3.0) < 1e-4


def test_profit_factor_zero_when_no_losses(logger):
    """All wins → gross_loss=0 → profit_factor=0.0 (no division)."""
    for _ in range(5):
        logger.log_trade(STRATEGY, 10.0)
    metrics = logger.compute_metrics(STRATEGY)
    assert metrics["profit_factor"] == 0.0


# ---------------------------------------------------------------------------
# compute_metrics — sharpe_ratio
# ---------------------------------------------------------------------------

def test_sharpe_zero_with_single_trade(logger):
    logger.log_trade(STRATEGY, 10.0)
    metrics = logger.compute_metrics(STRATEGY)
    assert metrics["sharpe_ratio"] == 0.0


def test_sharpe_nonzero_with_mixed_trades(logger):
    for pnl in [10.0, -5.0, 8.0, -3.0, 12.0]:
        logger.log_trade(STRATEGY, pnl)
    metrics = logger.compute_metrics(STRATEGY)
    assert metrics["sharpe_ratio"] != 0.0


# ---------------------------------------------------------------------------
# compute_metrics — max_drawdown
# ---------------------------------------------------------------------------

def test_max_drawdown_zero_for_all_wins(logger):
    for _ in range(5):
        logger.log_trade(STRATEGY, 5.0)
    metrics = logger.compute_metrics(STRATEGY)
    assert metrics["max_drawdown_eur"] == 0.0


def test_max_drawdown_negative_for_losses(logger):
    for pnl in [10.0, -20.0, 5.0]:
        logger.log_trade(STRATEGY, pnl)
    metrics = logger.compute_metrics(STRATEGY)
    assert metrics["max_drawdown_eur"] < 0.0


# ---------------------------------------------------------------------------
# update_stats — dashboard file
# ---------------------------------------------------------------------------

def test_update_stats_creates_dashboard_file(logger):
    logger.log_trade(STRATEGY, 5.0)
    logger.update_stats(STRATEGY, mode="paper")
    stats = logger.get_stats(mode="paper")
    assert STRATEGY in stats["strategies"]


def test_update_stats_result_has_required_fields(logger):
    logger.log_trade(STRATEGY, 5.0)
    result = logger.update_stats(STRATEGY)
    assert "strategy" in result
    assert "mode" in result
    assert "metrics" in result


def test_update_stats_persists_metrics(logger):
    _log_n_trades(logger, 10, win_pnl=10.0, loss_pnl=-5.0, win_rate=0.7)
    logger.update_stats(STRATEGY, mode="paper")
    stats = logger.get_stats("paper")
    entry = stats["strategies"][STRATEGY]
    assert entry["total_trades"] == 10
    assert entry["win_rate"] > 0.0


def test_update_stats_live_writes_to_live_file(logger):
    logger.log_trade(STRATEGY, 5.0, mode="live")
    logger.update_stats(STRATEGY, mode="live")
    stats = logger.get_stats(mode="live")
    assert STRATEGY in stats["strategies"]


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

def test_milestone_50_published(logger):
    store = PolyDataStore(base_path=logger.base_path)
    _log_n_trades(logger, 50)
    logger.update_stats(STRATEGY)
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "eval:milestone" in topics


def test_milestone_event_has_correct_milestone_count(logger):
    store = PolyDataStore(base_path=logger.base_path)
    _log_n_trades(logger, 50)
    logger.update_stats(STRATEGY)
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "eval:milestone")
    assert evt["payload"]["milestone"] == 50


def test_milestone_event_producer(logger):
    store = PolyDataStore(base_path=logger.base_path)
    _log_n_trades(logger, 50)
    logger.update_stats(STRATEGY)
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "eval:milestone")
    assert evt["producer"] == CONSUMER_ID


def test_milestone_event_includes_metrics(logger):
    store = PolyDataStore(base_path=logger.base_path)
    _log_n_trades(logger, 50)
    logger.update_stats(STRATEGY)
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "eval:milestone")
    assert "metrics" in evt["payload"]
    assert evt["payload"]["metrics"]["total_trades"] == 50


def test_milestone_not_fired_below_threshold(logger):
    store = PolyDataStore(base_path=logger.base_path)
    _log_n_trades(logger, 49)
    logger.update_stats(STRATEGY)
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "eval:milestone" not in topics


def test_milestone_not_fired_twice_for_same_threshold(logger):
    """Calling update_stats twice does not re-fire the same milestone."""
    store = PolyDataStore(base_path=logger.base_path)
    _log_n_trades(logger, 50)
    logger.update_stats(STRATEGY)   # fires milestone 50
    logger.update_stats(STRATEGY)   # same count — should NOT fire again
    events = store.read_jsonl("bus/pending_events.jsonl")
    milestone_events = [e for e in events if e.get("topic") == "eval:milestone"]
    assert len(milestone_events) == 1


def test_milestone_100_fired_after_100_trades(logger):
    store = PolyDataStore(base_path=logger.base_path)
    _log_n_trades(logger, 100)
    logger.update_stats(STRATEGY)
    events = store.read_jsonl("bus/pending_events.jsonl")
    milestones = [e["payload"]["milestone"] for e in events if e.get("topic") == "eval:milestone"]
    assert 100 in milestones


def test_milestone_audited(logger):
    _log_n_trades(logger, 50)
    logger.update_stats(STRATEGY)
    audit = PolyAuditLog(base_path=logger.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "eval:milestone" in topics


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

def test_get_stats_returns_empty_when_no_file(logger):
    stats = logger.get_stats()
    assert "strategies" in stats


def test_get_stats_returns_strategy_entry(logger):
    _log_n_trades(logger, 5)
    logger.update_stats(STRATEGY)
    stats = logger.get_stats()
    assert STRATEGY in stats["strategies"]


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------

def test_run_once_processes_all_strategies(logger):
    strategy_b = "POLY_WEATHER_ARB"
    _log_n_trades(logger, 5, strategy=STRATEGY)
    _log_n_trades(logger, 5, strategy=strategy_b)
    results = logger.run_once([STRATEGY, strategy_b])
    assert len(results) == 2
    strategies_in_results = [r["strategy"] for r in results]
    assert STRATEGY in strategies_in_results
    assert strategy_b in strategies_in_results


def test_run_once_empty_list_returns_empty(logger):
    results = logger.run_once([])
    assert results == []
