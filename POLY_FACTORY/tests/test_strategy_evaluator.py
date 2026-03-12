"""
Tests for POLY_STRATEGY_EVALUATOR (POLY-026).

Key acceptance criteria from ticket:
- Sharpe 2.5 + WR 85% → score > 70
- Sharpe 0.5 + WR 45% → score < 40
"""

import pytest
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_strategy_account import PolyStrategyAccount
from evaluation.poly_performance_logger import PolyPerformanceLogger
from evaluation.poly_strategy_evaluator import (
    PolyStrategyEvaluator,
    AXES_WEIGHTS,
    CONSUMER_ID,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def evaluator(tmp_path):
    return PolyStrategyEvaluator(base_path=str(tmp_path))


INITIAL_CAPITAL = 1000.0
STRATEGY = "POLY_ARB_SCANNER"
ACCOUNT_ID = "ACC_POLY_ARB_SCANNER"


def _make_metrics(
    total_trades=50,
    win_rate=0.65,
    total_pnl=50.0,
    profit_factor=2.0,
    sharpe_ratio=1.5,
    max_drawdown_eur=-50.0,
):
    return {
        "total_trades":    total_trades,
        "win_rate":        win_rate,
        "total_pnl":       total_pnl,
        "profit_factor":   profit_factor,
        "sharpe_ratio":    sharpe_ratio,
        "max_drawdown_eur": max_drawdown_eur,
    }


def _high_metrics():
    """High-performance metrics: Sharpe 2.5 + WR 85%."""
    return _make_metrics(
        total_trades=50,
        win_rate=0.85,
        total_pnl=100.0,   # 10% return on 1 000€
        profit_factor=2.5,
        sharpe_ratio=2.5,
        max_drawdown_eur=-50.0,  # -5%
    )


def _low_metrics():
    """Low-performance metrics: Sharpe 0.5 + WR 45%."""
    return _make_metrics(
        total_trades=20,
        win_rate=0.45,
        total_pnl=20.0,   # 2% return
        profit_factor=1.2,
        sharpe_ratio=0.5,
        max_drawdown_eur=-150.0,  # -15%
    )


# ---------------------------------------------------------------------------
# Ticket acceptance criteria
# ---------------------------------------------------------------------------

def test_high_performance_scores_above_70(evaluator):
    """Sharpe 2.5 + WR 85% → total score > 70."""
    axes = evaluator.score_axes(_high_metrics(), INITIAL_CAPITAL)
    score = evaluator.total_score(axes)
    assert score > 70, f"Expected score > 70, got {score}"


def test_low_performance_scores_below_40(evaluator):
    """Sharpe 0.5 + WR 45% → total score < 40."""
    axes = evaluator.score_axes(_low_metrics(), INITIAL_CAPITAL)
    score = evaluator.total_score(axes)
    assert score < 40, f"Expected score < 40, got {score}"


# ---------------------------------------------------------------------------
# score_axes — structure
# ---------------------------------------------------------------------------

def test_axis_scores_dict_has_8_keys(evaluator):
    axes = evaluator.score_axes(_make_metrics(), INITIAL_CAPITAL)
    assert len(axes) == 8
    assert set(axes.keys()) == set(AXES_WEIGHTS.keys())


def test_all_axis_scores_in_range_0_100(evaluator):
    axes = evaluator.score_axes(_make_metrics(), INITIAL_CAPITAL)
    for axis, score in axes.items():
        assert 0.0 <= score <= 100.0, f"Axis {axis} score {score} out of range"


def test_axis_scores_non_negative_for_any_input(evaluator):
    """Even poor metrics should produce scores ≥ 0."""
    poor = _make_metrics(
        total_trades=0, win_rate=0.0, total_pnl=-500.0,
        profit_factor=0.0, sharpe_ratio=-5.0, max_drawdown_eur=-1000.0,
    )
    axes = evaluator.score_axes(poor, INITIAL_CAPITAL)
    for axis, score in axes.items():
        assert score >= 0.0, f"Axis {axis} returned negative score {score}"


# ---------------------------------------------------------------------------
# score_axes — individual axes
# ---------------------------------------------------------------------------

def test_high_win_rate_gives_high_win_rate_score(evaluator):
    axes = evaluator.score_axes(_make_metrics(win_rate=1.0), INITIAL_CAPITAL)
    assert axes["win_rate"] == 100.0


def test_zero_win_rate_gives_zero_win_rate_score(evaluator):
    axes = evaluator.score_axes(_make_metrics(win_rate=0.0), INITIAL_CAPITAL)
    assert axes["win_rate"] == 0.0


def test_high_sharpe_gives_high_sharpe_score(evaluator):
    axes = evaluator.score_axes(_make_metrics(sharpe_ratio=3.0), INITIAL_CAPITAL)
    assert axes["sharpe"] >= 99.0


def test_zero_sharpe_gives_zero_sharpe_score(evaluator):
    axes = evaluator.score_axes(_make_metrics(sharpe_ratio=0.0), INITIAL_CAPITAL)
    assert axes["sharpe"] == 0.0


def test_backtest_malus_reduces_tradability(evaluator):
    m = _make_metrics(total_trades=50)
    axes_live = evaluator.score_axes(m, INITIAL_CAPITAL, is_backtest=False)
    axes_bt   = evaluator.score_axes(m, INITIAL_CAPITAL, is_backtest=True)
    assert axes_bt["tradability"] == axes_live["tradability"] - 15.0


def test_backtest_tradability_not_below_zero(evaluator):
    m = _make_metrics(total_trades=1)  # 2 points raw
    axes = evaluator.score_axes(m, INITIAL_CAPITAL, is_backtest=True)
    assert axes["tradability"] == 0.0


def test_positive_return_gives_profitability_score(evaluator):
    m = _make_metrics(total_pnl=100.0)  # 10% on 1000€
    axes = evaluator.score_axes(m, INITIAL_CAPITAL)
    assert axes["profitability"] == 100.0


def test_zero_drawdown_gives_max_drawdown_score(evaluator):
    m = _make_metrics(max_drawdown_eur=0.0)
    axes = evaluator.score_axes(m, INITIAL_CAPITAL)
    assert axes["drawdown"] == 100.0


def test_large_drawdown_reduces_drawdown_score(evaluator):
    m = _make_metrics(max_drawdown_eur=-500.0)  # -50% on 1000€
    axes = evaluator.score_axes(m, INITIAL_CAPITAL)
    assert axes["drawdown"] == 0.0


def test_50_trades_max_tradability(evaluator):
    axes = evaluator.score_axes(_make_metrics(total_trades=50), INITIAL_CAPITAL)
    assert axes["tradability"] == 100.0


# ---------------------------------------------------------------------------
# total_score
# ---------------------------------------------------------------------------

def test_total_score_uses_weights(evaluator):
    """Score of 100 on all axes should give total_score = 100."""
    axes = {axis: 100.0 for axis in AXES_WEIGHTS}
    score = evaluator.total_score(axes)
    assert abs(score - 100.0) < 0.01


def test_total_score_zero_for_all_zeros(evaluator):
    axes = {axis: 0.0 for axis in AXES_WEIGHTS}
    score = evaluator.total_score(axes)
    assert score == 0.0


# ---------------------------------------------------------------------------
# verdict_from_score
# ---------------------------------------------------------------------------

def test_verdict_star_at_75(evaluator):
    assert evaluator.verdict_from_score(75.0) == "STAR"


def test_verdict_star_at_100(evaluator):
    assert evaluator.verdict_from_score(100.0) == "STAR"


def test_verdict_solid_at_60(evaluator):
    assert evaluator.verdict_from_score(60.0) == "SOLID"


def test_verdict_solid_at_74(evaluator):
    assert evaluator.verdict_from_score(74.9) == "SOLID"


def test_verdict_fragile_at_40(evaluator):
    assert evaluator.verdict_from_score(40.0) == "FRAGILE"


def test_verdict_fragile_at_59(evaluator):
    assert evaluator.verdict_from_score(59.9) == "FRAGILE"


def test_verdict_declining_at_20(evaluator):
    assert evaluator.verdict_from_score(20.0) == "DECLINING"


def test_verdict_retire_at_19(evaluator):
    assert evaluator.verdict_from_score(19.9) == "RETIRE"


def test_verdict_retire_at_zero(evaluator):
    assert evaluator.verdict_from_score(0.0) == "RETIRE"


# ---------------------------------------------------------------------------
# evaluate — result structure
# ---------------------------------------------------------------------------

def test_evaluate_returns_result_dict(evaluator):
    result = evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    assert isinstance(result, dict)


def test_evaluate_result_has_required_fields(evaluator):
    result = evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    for field in ("strategy", "account_id", "score_total", "verdict",
                  "previous_score", "previous_verdict", "axes", "evaluated_at"):
        assert field in result


def test_evaluate_result_axes_has_8_keys(evaluator):
    result = evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    assert len(result["axes"]) == 8


def test_evaluate_previous_score_none_on_first_run(evaluator):
    result = evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    assert result["previous_score"] is None


def test_evaluate_previous_score_on_second_run(evaluator):
    evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    result2 = evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    assert result2["previous_score"] is not None


# ---------------------------------------------------------------------------
# evaluate — persistence
# ---------------------------------------------------------------------------

def test_evaluate_saves_to_scores_file(evaluator):
    evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    scores = evaluator.get_scores()
    assert STRATEGY in scores


def test_evaluate_updates_rankings(evaluator):
    evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    rankings = evaluator.get_rankings()
    assert len(rankings) == 1
    assert rankings[0]["strategy"] == STRATEGY


# ---------------------------------------------------------------------------
# evaluate — bus / audit
# ---------------------------------------------------------------------------

def test_evaluate_publishes_bus_event(evaluator):
    store = PolyDataStore(base_path=evaluator.base_path)
    evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "eval:score_updated" in topics


def test_evaluate_bus_event_producer(evaluator):
    store = PolyDataStore(base_path=evaluator.base_path)
    evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "eval:score_updated")
    assert evt["producer"] == CONSUMER_ID


def test_evaluate_bus_event_payload_fields(evaluator):
    store = PolyDataStore(base_path=evaluator.base_path)
    evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "eval:score_updated")
    payload = evt["payload"]
    for field in ("strategy", "account_id", "score_total", "verdict",
                  "previous_score", "previous_verdict", "axes"):
        assert field in payload


def test_evaluate_audit_logged(evaluator):
    evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    audit = PolyAuditLog(base_path=evaluator.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "eval:score_updated" in topics


# ---------------------------------------------------------------------------
# update_rankings
# ---------------------------------------------------------------------------

def test_rankings_sorted_by_score_descending(evaluator):
    evaluator.evaluate("STRAT_A", "ACC_STRAT_A", _high_metrics(),   INITIAL_CAPITAL)
    evaluator.evaluate("STRAT_B", "ACC_STRAT_B", _low_metrics(),    INITIAL_CAPITAL)
    rankings = evaluator.get_rankings()
    scores = [r["score_total"] for r in rankings]
    assert scores == sorted(scores, reverse=True)


def test_rankings_include_rank_field(evaluator):
    evaluator.evaluate(STRATEGY, ACCOUNT_ID, _make_metrics(), INITIAL_CAPITAL)
    rankings = evaluator.get_rankings()
    assert rankings[0]["rank"] == 1


def test_rankings_rank_starts_at_1(evaluator):
    evaluator.evaluate("STRAT_A", "ACC_STRAT_A", _make_metrics(), INITIAL_CAPITAL)
    evaluator.evaluate("STRAT_B", "ACC_STRAT_B", _make_metrics(), INITIAL_CAPITAL)
    rankings = evaluator.get_rankings()
    ranks = [r["rank"] for r in rankings]
    assert 1 in ranks


def test_get_rankings_returns_list(evaluator):
    assert isinstance(evaluator.get_rankings(), list)


def test_get_scores_returns_dict(evaluator):
    assert isinstance(evaluator.get_scores(), dict)


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------

def test_run_once_evaluates_strategy_with_account_and_trades(evaluator):
    """run_once loads account + metrics and calls evaluate() automatically."""
    # Create account
    PolyStrategyAccount.create(STRATEGY, "polymarket", base_path=evaluator.base_path)
    # Log 10 trades via PerformanceLogger
    logger = PolyPerformanceLogger(
        base_path=evaluator.base_path,
        dashboard_path=str(evaluator.base_path + "/dashboard"),
    )
    for i in range(10):
        logger.log_trade(STRATEGY, 5.0 if i % 2 == 0 else -2.0)

    results = evaluator.run_once([STRATEGY])
    assert len(results) == 1
    assert results[0]["strategy"] == STRATEGY


def test_run_once_skips_strategy_without_account(evaluator):
    """Strategies with no account file are skipped silently."""
    results = evaluator.run_once(["POLY_GHOST_STRATEGY"])
    assert results == []


def test_run_once_skips_strategy_with_no_trades(evaluator):
    """Strategies with zero trades are skipped (no meaningful score)."""
    PolyStrategyAccount.create(STRATEGY, "polymarket", base_path=evaluator.base_path)
    results = evaluator.run_once([STRATEGY])
    assert results == []


def test_run_once_empty_list_returns_empty(evaluator):
    assert evaluator.run_once([]) == []
