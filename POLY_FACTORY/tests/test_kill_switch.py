"""
Tests for POLY_KILL_SWITCH (POLY-021).

Key acceptance criteria from ticket:
- drawdown -6% → triggered (PAUSE_DAILY)
- 3 consecutive losses → pause (PAUSE_DAILY)
- PM_FEED stale → pause session (PAUSE_SESSION)
- reset midnight → daily state cleared
"""

import pytest
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_strategy_account import PolyStrategyAccount
from risk.poly_kill_switch import (
    PolyKillSwitch,
    LEVEL_OK,
    LEVEL_WARNING,
    LEVEL_PAUSE_DAILY,
    LEVEL_PAUSE_SESSION,
    LEVEL_STOP_STRATEGY,
    DAILY_DRAWDOWN_LIMIT_PCT,
    TOTAL_DRAWDOWN_LIMIT_PCT,
    MAX_CONSECUTIVE_LOSSES,
    FEED_STALE_THRESHOLD_SECONDS,
    WARNING_RATIO,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRATEGY = "POLY_ARB_SCANNER"
ACCOUNT_ID = "ACC_POLY_ARB_SCANNER"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base(tmp_path):
    return str(tmp_path)


@pytest.fixture
def account(base):
    return PolyStrategyAccount.create(
        strategy=STRATEGY, platform="polymarket", base_path=base
    )


@pytest.fixture
def ks(base):
    return PolyKillSwitch(base_path=base)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_account_with_daily_loss(base, pct):
    """Create account and record a single trade causing `pct`% daily loss."""
    acct = PolyStrategyAccount.create(
        strategy=STRATEGY, platform="polymarket", base_path=base
    )
    loss = acct.data["capital"]["initial"] * abs(pct) / 100.0
    acct.record_trade(-loss)
    return acct


def _make_account_with_total_loss(base, pct):
    """Create account and record a single trade causing `pct`% total drawdown."""
    acct = PolyStrategyAccount.create(
        strategy=STRATEGY, platform="polymarket", base_path=base
    )
    loss = acct.data["capital"]["initial"] * abs(pct) / 100.0
    acct.record_trade(-loss)
    return acct


# ---------------------------------------------------------------------------
# Daily drawdown trigger (ticket: drawdown -6% → déclenché)
# ---------------------------------------------------------------------------

def test_evaluate_triggers_on_daily_drawdown(base, ks):
    """daily_pnl_pct = -6% < -5% limit → PAUSE_DAILY."""
    _make_account_with_daily_loss(base, 6.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["level"] == LEVEL_PAUSE_DAILY


def test_evaluate_action_pause_on_daily_drawdown(base, ks):
    _make_account_with_daily_loss(base, 6.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["action"] == "pause_strategy"


def test_evaluate_reason_daily_drawdown(base, ks):
    _make_account_with_daily_loss(base, 6.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["reason"] == "daily_drawdown_exceeded"


def test_evaluate_ok_when_within_daily_limit(base, ks):
    """daily_pnl_pct = -4% < -5% limit (but > -5%) → OK (or WARNING)."""
    _make_account_with_daily_loss(base, 4.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["level"] in (LEVEL_OK, LEVEL_WARNING)


def test_evaluate_ok_when_no_losses(base, ks):
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["level"] == LEVEL_OK


def test_evaluate_resume_at_set_on_daily_pause(base, ks):
    _make_account_with_daily_loss(base, 6.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["resume_at"] is not None


# ---------------------------------------------------------------------------
# Total drawdown trigger
# ---------------------------------------------------------------------------

def test_evaluate_triggers_stop_on_total_drawdown(base, ks):
    """current_drawdown_pct = -31% < -30% limit → STOP_STRATEGY."""
    _make_account_with_total_loss(base, 31.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["level"] == LEVEL_STOP_STRATEGY


def test_evaluate_action_stop_on_total_drawdown(base, ks):
    _make_account_with_total_loss(base, 31.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["action"] == "stop_strategy"


def test_evaluate_resume_at_none_on_stop(base, ks):
    _make_account_with_total_loss(base, 31.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["resume_at"] is None


def test_total_drawdown_priority_over_daily(base, ks):
    """Total drawdown takes priority over daily drawdown."""
    acct = PolyStrategyAccount.create(
        strategy=STRATEGY, platform="polymarket", base_path=base
    )
    # Record loss that exceeds BOTH daily and total limits
    acct.record_trade(-310.0)   # current_dd = -31%, daily_pnl_pct = -31%
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["level"] == LEVEL_STOP_STRATEGY


# ---------------------------------------------------------------------------
# Consecutive losses trigger (ticket: 3 pertes → pause)
# ---------------------------------------------------------------------------

def test_three_consecutive_losses_pause(base, ks):
    """3 consecutive losses → PAUSE_DAILY."""
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    for _ in range(MAX_CONSECUTIVE_LOSSES):
        ks.record_trade_result(STRATEGY, -5.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["level"] == LEVEL_PAUSE_DAILY


def test_three_consecutive_losses_reason(base, ks):
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    for _ in range(MAX_CONSECUTIVE_LOSSES):
        ks.record_trade_result(STRATEGY, -5.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["reason"] == "consecutive_losses_exceeded"


def test_consecutive_losses_reset_on_win(base, ks):
    """Two losses then a win → counter resets → no trigger."""
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    ks.record_trade_result(STRATEGY, -5.0)
    ks.record_trade_result(STRATEGY, -5.0)
    ks.record_trade_result(STRATEGY, +10.0)  # win: resets counter
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["level"] == LEVEL_OK


def test_two_losses_no_trigger(base, ks):
    """Two losses (below threshold of 3) → no trigger."""
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    ks.record_trade_result(STRATEGY, -5.0)
    ks.record_trade_result(STRATEGY, -5.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["level"] in (LEVEL_OK, LEVEL_WARNING)


# ---------------------------------------------------------------------------
# Feed staleness trigger (ticket: PM_FEED stale → stop)
# ---------------------------------------------------------------------------

def test_feed_stale_triggers_pause_session(base, ks):
    """Feed age > threshold → PAUSE_SESSION."""
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    result = ks.check_feed_health(STRATEGY, ACCOUNT_ID,
                                   feed_age_seconds=FEED_STALE_THRESHOLD_SECONDS + 1)
    assert result["level"] == LEVEL_PAUSE_SESSION


def test_feed_stale_action(base, ks):
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    result = ks.check_feed_health(STRATEGY, ACCOUNT_ID,
                                   feed_age_seconds=FEED_STALE_THRESHOLD_SECONDS + 1)
    assert result["action"] == "pause_strategy"


def test_feed_fresh_no_trigger(base, ks):
    """Feed age within threshold → no pause."""
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    result = ks.check_feed_health(STRATEGY, ACCOUNT_ID,
                                   feed_age_seconds=FEED_STALE_THRESHOLD_SECONDS - 1)
    assert result["level"] not in (LEVEL_PAUSE_SESSION, LEVEL_STOP_STRATEGY)


def test_feed_recovery_resumes_session(base, ks):
    """Stale → fresh → PAUSE_SESSION cleared to OK."""
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    ks.check_feed_health(STRATEGY, ACCOUNT_ID,
                         feed_age_seconds=FEED_STALE_THRESHOLD_SECONDS + 60)
    result = ks.check_feed_health(STRATEGY, ACCOUNT_ID,
                                   feed_age_seconds=10)
    assert result["level"] == LEVEL_OK


# ---------------------------------------------------------------------------
# Warning level
# ---------------------------------------------------------------------------

def test_warning_level_approaching_daily_limit(base, ks):
    """Daily P&L at 85% of limit (> 80% threshold) → WARNING."""
    acct = PolyStrategyAccount.create(
        strategy=STRATEGY, platform="polymarket", base_path=base
    )
    # -4.5% daily: below WARNING threshold (-4.0%) but above PAUSE threshold (-5.0%)
    acct.record_trade(-45.0)
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["level"] == LEVEL_WARNING


def test_no_warning_far_from_limit(base, ks):
    """Daily P&L well within limits → OK, not WARNING."""
    acct = PolyStrategyAccount.create(
        strategy=STRATEGY, platform="polymarket", base_path=base
    )
    acct.record_trade(-10.0)  # only -1% loss
    result = ks.evaluate(STRATEGY, ACCOUNT_ID)
    assert result["level"] == LEVEL_OK


# ---------------------------------------------------------------------------
# Pre-trade check
# ---------------------------------------------------------------------------

def test_pre_trade_allowed_when_ok(base, ks):
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    result = ks.check_pre_trade(STRATEGY)
    assert result["allowed"] is True
    assert result["level"] == LEVEL_OK


def test_pre_trade_blocked_after_daily_pause(base, ks):
    _make_account_with_daily_loss(base, 6.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    result = ks.check_pre_trade(STRATEGY)
    assert result["allowed"] is False


def test_pre_trade_blocked_after_stop(base, ks):
    _make_account_with_total_loss(base, 31.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    result = ks.check_pre_trade(STRATEGY)
    assert result["allowed"] is False


def test_pre_trade_blocked_after_feed_stale(base, ks):
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    ks.check_feed_health(STRATEGY, ACCOUNT_ID,
                         feed_age_seconds=FEED_STALE_THRESHOLD_SECONDS + 1)
    result = ks.check_pre_trade(STRATEGY)
    assert result["allowed"] is False


def test_pre_trade_allowed_during_warning(base, ks):
    """WARNING level → trading still allowed."""
    acct = PolyStrategyAccount.create(
        strategy=STRATEGY, platform="polymarket", base_path=base
    )
    acct.record_trade(-45.0)  # -4.5%, triggers WARNING
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    result = ks.check_pre_trade(STRATEGY)
    assert result["allowed"] is True


# ---------------------------------------------------------------------------
# Daily reset (ticket: reset minuit)
# ---------------------------------------------------------------------------

def test_reset_daily_clears_pause_daily(base, ks):
    """After reset, PAUSE_DAILY → OK."""
    _make_account_with_daily_loss(base, 6.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    ks.reset_daily(STRATEGY)
    result = ks.check_pre_trade(STRATEGY)
    assert result["allowed"] is True
    assert result["level"] == LEVEL_OK


def test_reset_daily_clears_consecutive_losses(base, ks):
    """After reset, consecutive_losses returns to 0."""
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    for _ in range(MAX_CONSECUTIVE_LOSSES):
        ks.record_trade_result(STRATEGY, -5.0)
    ks.reset_daily(STRATEGY)
    with ks._lock:
        count = ks._status.get(STRATEGY, {}).get("consecutive_losses", -1)
    assert count == 0


def test_reset_daily_does_not_clear_stop_strategy(base, ks):
    """STOP_STRATEGY is permanent — reset_daily must not clear it."""
    _make_account_with_total_loss(base, 31.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    ks.reset_daily(STRATEGY)
    result = ks.check_pre_trade(STRATEGY)
    assert result["allowed"] is False
    assert result["level"] == LEVEL_STOP_STRATEGY


def test_reset_daily_then_evaluate_ok_after_account_reset(base, ks):
    """Full midnight sequence: account reset + kill switch reset → OK."""
    acct = _make_account_with_daily_loss(base, 6.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)         # → PAUSE_DAILY
    acct.reset_daily()                          # reset account daily P&L
    ks.reset_daily(STRATEGY)                   # reset kill switch state
    result = ks.evaluate(STRATEGY, ACCOUNT_ID) # fresh evaluation
    assert result["level"] == LEVEL_OK


# ---------------------------------------------------------------------------
# Bus and audit integration
# ---------------------------------------------------------------------------

def test_bus_event_published_on_trigger(base, ks):
    store = PolyDataStore(base_path=base)
    _make_account_with_daily_loss(base, 6.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "risk:kill_switch" in topics


def test_bus_event_priority_high(base, ks):
    store = PolyDataStore(base_path=base)
    _make_account_with_daily_loss(base, 6.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    events = store.read_jsonl("bus/pending_events.jsonl")
    ks_events = [e for e in events if e.get("topic") == "risk:kill_switch"]
    assert all(e.get("priority") == "high" for e in ks_events)


def test_bus_event_payload_fields(base, ks):
    store = PolyDataStore(base_path=base)
    _make_account_with_daily_loss(base, 6.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    events = store.read_jsonl("bus/pending_events.jsonl")
    payload = next(e["payload"] for e in events if e.get("topic") == "risk:kill_switch")
    for field in ("action", "strategy", "account_id", "reason",
                  "drawdown_pct", "threshold_pct", "resume_at"):
        assert field in payload


def test_audit_logged_on_trigger(base, ks):
    _make_account_with_daily_loss(base, 6.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    audit = PolyAuditLog(base_path=base)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "risk:kill_switch" in topics


def test_status_persisted_to_disk(base, ks):
    """kill_switch_status.json must be updated on trigger."""
    store = PolyDataStore(base_path=base)
    _make_account_with_daily_loss(base, 6.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    status = store.read_json("risk/kill_switch_status.json")
    assert STRATEGY in status
    assert status[STRATEGY]["level"] == LEVEL_PAUSE_DAILY


def test_dedup_no_double_bus_event(base, ks):
    """Calling evaluate() twice with same condition → only one bus event."""
    store = PolyDataStore(base_path=base)
    _make_account_with_daily_loss(base, 6.0)
    ks.evaluate(STRATEGY, ACCOUNT_ID)
    ks.evaluate(STRATEGY, ACCOUNT_ID)  # same condition → dedup
    events = store.read_jsonl("bus/pending_events.jsonl")
    ks_events = [e for e in events if e.get("topic") == "risk:kill_switch"]
    assert len(ks_events) == 1


# ---------------------------------------------------------------------------
# Register and run_once
# ---------------------------------------------------------------------------

def test_register_adds_to_status(base, ks):
    ks.register(STRATEGY, ACCOUNT_ID)
    with ks._lock:
        assert STRATEGY in ks._status


def test_run_once_returns_triggered_strategies(base, ks):
    _make_account_with_daily_loss(base, 6.0)
    ks.register(STRATEGY, ACCOUNT_ID)
    results = ks.run_once()
    assert len(results) == 1
    assert results[0]["level"] == LEVEL_PAUSE_DAILY


def test_run_once_returns_empty_when_all_ok(base, ks):
    PolyStrategyAccount.create(strategy=STRATEGY, platform="polymarket", base_path=base)
    ks.register(STRATEGY, ACCOUNT_ID)
    results = ks.run_once()
    assert results == []


def test_run_once_skips_missing_accounts(base, ks):
    """run_once should not crash if account file is missing."""
    ks.register("POLY_GHOST", "ACC_POLY_GHOST")
    results = ks.run_once()
    assert isinstance(results, list)
