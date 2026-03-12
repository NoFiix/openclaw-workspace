"""
Tests for POLY_GLOBAL_RISK_GUARD (POLY-023).

Key acceptance criteria from ticket:
- Progressive losses → verify each transition NORMAL/ALERTE/CRITIQUE/ARRET_TOTAL
"""

import pytest
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_strategy_account import PolyStrategyAccount
from risk.poly_global_risk_guard import (
    PolyGlobalRiskGuard,
    MAX_LOSS_EUR,
    ALERTE_THRESHOLD_EUR,
    CRITIQUE_THRESHOLD_EUR,
    STATUS_NORMAL,
    STATUS_ALERTE,
    STATUS_CRITIQUE,
    STATUS_ARRET_TOTAL,
    CONSUMER_ID,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def guard(tmp_path):
    return PolyGlobalRiskGuard(base_path=str(tmp_path))


def _register_account_with_loss(guard, account_id, loss_eur):
    """Create a PolyStrategyAccount, apply a loss, and register it with the guard."""
    strategy = account_id.removeprefix("ACC_")
    account = PolyStrategyAccount.create(strategy, "polymarket", base_path=guard.base_path)
    if loss_eur > 0:
        account.record_trade(-loss_eur)   # negative pnl = loss
    guard.register(account_id)
    return account


def _register_account_with_profit(guard, account_id, profit_eur):
    """Create a PolyStrategyAccount with a positive P&L and register it."""
    strategy = account_id.removeprefix("ACC_")
    account = PolyStrategyAccount.create(strategy, "polymarket", base_path=guard.base_path)
    if profit_eur > 0:
        account.record_trade(profit_eur)
    guard.register(account_id)
    return account


# ---------------------------------------------------------------------------
# Ticket acceptance criteria — progressive transitions
# ---------------------------------------------------------------------------

def test_transitions_through_all_statuses(guard):
    """Progressive losses trigger NORMAL → ALERTE → CRITIQUE → ARRET_TOTAL."""
    account = _register_account_with_loss(guard, "ACC_STRAT_A", 0.0)

    # NORMAL (no loss yet)
    result = guard.evaluate()
    assert result["status"] == STATUS_NORMAL

    # Push to ALERTE (2 000€)
    account.record_trade(-2000.0)
    result = guard.evaluate()
    assert result["status"] == STATUS_ALERTE

    # Push to CRITIQUE (3 000€)
    account.record_trade(-1000.0)
    result = guard.evaluate()
    assert result["status"] == STATUS_CRITIQUE

    # Push to ARRET_TOTAL (4 000€)
    account.record_trade(-1000.0)
    result = guard.evaluate()
    assert result["status"] == STATUS_ARRET_TOTAL


# ---------------------------------------------------------------------------
# Status thresholds
# ---------------------------------------------------------------------------

def test_normal_with_no_registered_accounts(guard):
    result = guard.evaluate()
    assert result["status"] == STATUS_NORMAL


def test_normal_below_alerte(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", 1999.99)
    result = guard.evaluate()
    assert result["status"] == STATUS_NORMAL


def test_alerte_at_exactly_2000(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", ALERTE_THRESHOLD_EUR)
    result = guard.evaluate()
    assert result["status"] == STATUS_ALERTE


def test_alerte_within_range(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", 2500.0)
    result = guard.evaluate()
    assert result["status"] == STATUS_ALERTE


def test_critique_at_exactly_3000(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", CRITIQUE_THRESHOLD_EUR)
    result = guard.evaluate()
    assert result["status"] == STATUS_CRITIQUE


def test_critique_within_range(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", 3500.0)
    result = guard.evaluate()
    assert result["status"] == STATUS_CRITIQUE


def test_arret_total_at_exactly_4000(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", MAX_LOSS_EUR)
    result = guard.evaluate()
    assert result["status"] == STATUS_ARRET_TOTAL


def test_arret_total_above_threshold(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", 5000.0)
    result = guard.evaluate()
    assert result["status"] == STATUS_ARRET_TOTAL


# ---------------------------------------------------------------------------
# Loss calculation — only losses count, profits excluded
# ---------------------------------------------------------------------------

def test_profitable_account_not_counted(guard):
    """An account with positive P&L does not contribute to total loss."""
    _register_account_with_profit(guard, "ACC_STRAT_A", 3000.0)
    result = guard.evaluate()
    assert result["status"] == STATUS_NORMAL
    assert result["total_loss_eur"] == 0.0


def test_only_losing_accounts_contribute(guard):
    """Sum only negative P&L accounts; positive accounts are ignored."""
    _register_account_with_loss(guard, "ACC_STRAT_A", 1500.0)
    _register_account_with_profit(guard, "ACC_STRAT_B", 3000.0)
    result = guard.evaluate()
    assert result["total_loss_eur"] == 1500.0
    assert result["status"] == STATUS_NORMAL


def test_multiple_losing_accounts_sum(guard):
    """Total loss is the sum of losses from all losing accounts."""
    _register_account_with_loss(guard, "ACC_STRAT_A", 1200.0)
    _register_account_with_loss(guard, "ACC_STRAT_B", 900.0)
    result = guard.evaluate()
    assert abs(result["total_loss_eur"] - 2100.0) < 0.01
    assert result["status"] == STATUS_ALERTE


# ---------------------------------------------------------------------------
# Action taken
# ---------------------------------------------------------------------------

def test_action_none_when_normal(guard):
    result = guard.evaluate()
    assert result["action_taken"] == "none"


def test_action_block_promotions_when_alerte(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", ALERTE_THRESHOLD_EUR)
    result = guard.evaluate()
    assert result["action_taken"] == "block_new_live_promotions"


def test_action_block_promotions_when_critique(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", CRITIQUE_THRESHOLD_EUR)
    result = guard.evaluate()
    assert result["action_taken"] == "block_new_live_promotions"


def test_action_halt_trading_when_arret_total(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", MAX_LOSS_EUR)
    result = guard.evaluate()
    assert result["action_taken"] == "halt_all_trading"


# ---------------------------------------------------------------------------
# check_pre_trade
# ---------------------------------------------------------------------------

def test_check_pre_trade_allowed_when_normal(guard):
    result = guard.check_pre_trade()
    assert result["allowed"] is True


def test_check_pre_trade_allowed_when_alerte(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", ALERTE_THRESHOLD_EUR)
    guard.evaluate()
    result = guard.check_pre_trade()
    assert result["allowed"] is True


def test_check_pre_trade_allowed_when_critique(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", CRITIQUE_THRESHOLD_EUR)
    guard.evaluate()
    result = guard.check_pre_trade()
    assert result["allowed"] is True


def test_check_pre_trade_blocked_when_arret_total(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", MAX_LOSS_EUR)
    guard.evaluate()
    result = guard.check_pre_trade()
    assert result["allowed"] is False


def test_check_pre_trade_returns_status(guard):
    result = guard.check_pre_trade()
    assert "status" in result


def test_check_pre_trade_returns_reason_when_blocked(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", MAX_LOSS_EUR)
    guard.evaluate()
    result = guard.check_pre_trade()
    assert result["reason"] == "global_loss_limit_reached"


def test_check_pre_trade_reason_none_when_allowed(guard):
    result = guard.check_pre_trade()
    assert result["reason"] is None


# ---------------------------------------------------------------------------
# Bus and audit integration
# ---------------------------------------------------------------------------

def test_bus_event_published_on_status_change(guard):
    store = PolyDataStore(base_path=guard.base_path)
    _register_account_with_loss(guard, "ACC_STRAT_A", ALERTE_THRESHOLD_EUR)
    guard.evaluate()   # NORMAL → ALERTE: should publish
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "risk:global_status" in topics


def test_no_bus_event_if_status_unchanged(guard):
    store = PolyDataStore(base_path=guard.base_path)
    _register_account_with_loss(guard, "ACC_STRAT_A", 500.0)
    guard.evaluate()   # NORMAL → NORMAL (no change, no event)
    guard.evaluate()   # NORMAL → NORMAL again (still no event)
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "risk:global_status" not in topics


def test_bus_event_producer(guard):
    store = PolyDataStore(base_path=guard.base_path)
    _register_account_with_loss(guard, "ACC_STRAT_A", ALERTE_THRESHOLD_EUR)
    guard.evaluate()
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "risk:global_status")
    assert evt["producer"] == CONSUMER_ID


def test_audit_logged_on_status_change(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", ALERTE_THRESHOLD_EUR)
    guard.evaluate()
    audit = PolyAuditLog(base_path=guard.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "risk:global_status" in topics


# ---------------------------------------------------------------------------
# Result fields
# ---------------------------------------------------------------------------

def test_result_has_all_required_fields(guard):
    result = guard.evaluate()
    for field in ("status", "total_loss_eur", "max_loss_eur", "pct_used",
                  "action_taken", "accounts_contributing"):
        assert field in result


def test_max_loss_eur_in_result(guard):
    result = guard.evaluate()
    assert result["max_loss_eur"] == MAX_LOSS_EUR


def test_pct_used_computed_correctly(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", 2000.0)
    result = guard.evaluate()
    assert abs(result["pct_used"] - 0.5) < 1e-4


def test_accounts_contributing_in_result(guard):
    _register_account_with_loss(guard, "ACC_STRAT_A", 1500.0)
    result = guard.evaluate()
    assert "ACC_STRAT_A" in result["accounts_contributing"]
    assert result["accounts_contributing"]["ACC_STRAT_A"] < 0


def test_profitable_account_not_in_contributing(guard):
    _register_account_with_profit(guard, "ACC_STRAT_A", 500.0)
    result = guard.evaluate()
    assert "ACC_STRAT_A" not in result["accounts_contributing"]


# ---------------------------------------------------------------------------
# Registration and state
# ---------------------------------------------------------------------------

def test_register_adds_account(guard):
    guard.register("ACC_STRAT_A")
    state = guard.get_state()
    assert "ACC_STRAT_A" in state["registered_accounts"]


def test_register_is_idempotent(guard):
    guard.register("ACC_STRAT_A")
    guard.register("ACC_STRAT_A")
    state = guard.get_state()
    assert state["registered_accounts"].count("ACC_STRAT_A") == 1


def test_state_persisted_after_evaluate(guard):
    store = PolyDataStore(base_path=guard.base_path)
    _register_account_with_loss(guard, "ACC_STRAT_A", ALERTE_THRESHOLD_EUR)
    guard.evaluate()
    state = store.read_json("risk/global_risk_state.json")
    assert state["status"] == STATUS_ALERTE


def test_get_state_returns_snapshot(guard):
    guard.evaluate()
    state = guard.get_state()
    assert "status" in state
    assert "total_loss_eur" in state


def test_unknown_account_skipped_silently(guard):
    """Registering an account that doesn't exist on disk does not crash."""
    guard.register("ACC_GHOST_STRATEGY")
    result = guard.evaluate()
    assert result["status"] == STATUS_NORMAL
    assert result["total_loss_eur"] == 0.0


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------

def test_run_once_returns_result_dict(guard):
    result = guard.run_once()
    assert isinstance(result, dict)
    assert "status" in result
