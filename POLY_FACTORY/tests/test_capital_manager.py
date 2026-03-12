"""
Tests for POLY_CAPITAL_MANAGER (POLY-024).

Key acceptance criteria from ticket:
- promotion:approved → account created
- trade > capital → blocked
- strategy stopped → capital recovered
"""

import pytest
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_strategy_account import PolyStrategyAccount
from risk.poly_capital_manager import PolyCapitalManager, CONSUMER_ID


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def manager(tmp_path):
    return PolyCapitalManager(base_path=str(tmp_path))


def _make_promotion_payload(strategy="POLY_ARB_SCANNER", initial_capital=1000.0):
    return {
        "strategy": strategy,
        "approval_id": "POLY_LIVE_001",
        "checks_passed": 10,
        "initial_capital_eur": initial_capital,
        "max_per_trade_eur": 50,
        "kill_switch_daily_pct": -0.03,
    }


def _create_paper_account(manager, strategy="POLY_ARB_SCANNER", capital=1000.0):
    """Create a paper testing account for the given strategy."""
    return PolyStrategyAccount.create(
        strategy, "polymarket",
        base_path=manager.base_path,
        initial_capital=capital,
    )


def _publish_promotion_approved(manager, payload):
    manager.bus.publish("promotion:approved", "POLY_STRATEGY_PROMOTION_GATE", payload)


def _publish_kill_switch_stop(manager, strategy, account_id):
    payload = {
        "action": "stop_strategy",
        "strategy": strategy,
        "account_id": account_id,
        "reason": "total_drawdown_exceeded",
        "drawdown_pct": -35.0,
        "threshold_pct": -30.0,
        "resume_at": None,
    }
    manager.bus.publish("risk:kill_switch", "POLY_KILL_SWITCH", payload, priority="high")


def _publish_kill_switch_pause(manager, strategy, account_id):
    payload = {
        "action": "pause_strategy",
        "strategy": strategy,
        "account_id": account_id,
        "reason": "daily_drawdown_exceeded",
        "drawdown_pct": -5.2,
        "threshold_pct": -5.0,
        "resume_at": "2026-03-13T00:00:00Z",
    }
    manager.bus.publish("risk:kill_switch", "POLY_KILL_SWITCH", payload, priority="high")


# ---------------------------------------------------------------------------
# Ticket acceptance criteria
# ---------------------------------------------------------------------------

def test_run_once_creates_live_account_on_promotion_approved(manager):
    """promotion:approved → live account created with status 'active'."""
    _publish_promotion_approved(manager, _make_promotion_payload())
    result = manager.run_once()
    assert len(result["created"]) == 1
    account = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", manager.base_path)
    assert account.status == "active"


def test_check_capital_blocked_when_size_exceeds_available(manager):
    """trade > capital → blocked."""
    _create_paper_account(manager, capital=100.0)
    result = manager.check_capital("ACC_POLY_ARB_SCANNER", size_eur=150.0)
    assert result["allowed"] is False


def test_recover_capital_archives_account(manager):
    """strategy stopped → capital recovered (account archived)."""
    _create_paper_account(manager)
    result = manager.recover_capital("POLY_ARB_SCANNER", "ACC_POLY_ARB_SCANNER")
    assert result["status"] == "stopped"
    # Account should now be archived (no longer loadable from active path)
    store = PolyDataStore(base_path=manager.base_path)
    assert not store.exists("accounts/ACC_POLY_ARB_SCANNER.json")


# ---------------------------------------------------------------------------
# create_live_account
# ---------------------------------------------------------------------------

def test_create_live_account_creates_account(manager):
    payload = _make_promotion_payload()
    manager.create_live_account(payload)
    account = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", manager.base_path)
    assert account is not None


def test_create_live_account_sets_status_active(manager):
    manager.create_live_account(_make_promotion_payload())
    account = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", manager.base_path)
    assert account.status == "active"


def test_create_live_account_uses_initial_capital_from_payload(manager):
    manager.create_live_account(_make_promotion_payload(initial_capital=2000.0))
    account = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", manager.base_path)
    assert account.data["capital"]["initial"] == 2000.0


def test_create_live_account_archives_existing_paper_account(manager):
    """If a paper account already exists, it is archived before creating live."""
    _create_paper_account(manager)
    manager.create_live_account(_make_promotion_payload())
    # After promotion, the new account should be loadable and active
    account = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", manager.base_path)
    assert account.status == "active"


def test_create_live_account_result_has_required_fields(manager):
    result = manager.create_live_account(_make_promotion_payload())
    for field in ("account_id", "strategy", "initial_capital_eur", "status"):
        assert field in result


def test_create_live_account_result_account_id(manager):
    result = manager.create_live_account(_make_promotion_payload())
    assert result["account_id"] == "ACC_POLY_ARB_SCANNER"


def test_create_live_account_publishes_bus_event(manager):
    store = PolyDataStore(base_path=manager.base_path)
    manager.create_live_account(_make_promotion_payload())
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "account:live_created" in topics


def test_create_live_account_bus_event_producer(manager):
    store = PolyDataStore(base_path=manager.base_path)
    manager.create_live_account(_make_promotion_payload())
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "account:live_created")
    assert evt["producer"] == CONSUMER_ID


def test_create_live_account_audits_event(manager):
    manager.create_live_account(_make_promotion_payload())
    audit = PolyAuditLog(base_path=manager.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "account:live_created" in topics


# ---------------------------------------------------------------------------
# check_capital
# ---------------------------------------------------------------------------

def test_check_capital_allowed_when_sufficient(manager):
    _create_paper_account(manager, capital=1000.0)
    result = manager.check_capital("ACC_POLY_ARB_SCANNER", size_eur=50.0)
    assert result["allowed"] is True


def test_check_capital_allowed_at_exact_limit(manager):
    """size_eur exactly equals available capital → allowed."""
    _create_paper_account(manager, capital=50.0)
    result = manager.check_capital("ACC_POLY_ARB_SCANNER", size_eur=50.0)
    assert result["allowed"] is True


def test_check_capital_blocked_just_above_available(manager):
    _create_paper_account(manager, capital=50.0)
    result = manager.check_capital("ACC_POLY_ARB_SCANNER", size_eur=50.01)
    assert result["allowed"] is False


def test_check_capital_blocked_when_account_not_found(manager):
    result = manager.check_capital("ACC_GHOST", size_eur=50.0)
    assert result["allowed"] is False
    assert result["reason"] == "account_not_found"


def test_check_capital_result_has_required_fields(manager):
    _create_paper_account(manager)
    result = manager.check_capital("ACC_POLY_ARB_SCANNER", size_eur=50.0)
    for field in ("allowed", "available_capital_eur", "required_eur", "reason"):
        assert field in result


def test_check_capital_returns_available_amount(manager):
    _create_paper_account(manager, capital=800.0)
    result = manager.check_capital("ACC_POLY_ARB_SCANNER", size_eur=100.0)
    assert result["available_capital_eur"] == 800.0


def test_check_capital_returns_required_amount(manager):
    _create_paper_account(manager, capital=1000.0)
    result = manager.check_capital("ACC_POLY_ARB_SCANNER", size_eur=75.0)
    assert result["required_eur"] == 75.0


def test_check_capital_reason_none_when_allowed(manager):
    _create_paper_account(manager, capital=1000.0)
    result = manager.check_capital("ACC_POLY_ARB_SCANNER", size_eur=50.0)
    assert result["reason"] is None


def test_check_capital_reason_insufficient_when_blocked(manager):
    _create_paper_account(manager, capital=10.0)
    result = manager.check_capital("ACC_POLY_ARB_SCANNER", size_eur=50.0)
    assert result["reason"] == "insufficient_capital"


# ---------------------------------------------------------------------------
# recover_capital
# ---------------------------------------------------------------------------

def test_recover_capital_result_has_required_fields(manager):
    _create_paper_account(manager)
    result = manager.recover_capital("POLY_ARB_SCANNER", "ACC_POLY_ARB_SCANNER")
    for field in ("strategy", "account_id", "recovered_capital_eur", "status"):
        assert field in result


def test_recover_capital_returns_current_capital(manager):
    _create_paper_account(manager, capital=800.0)
    result = manager.recover_capital("POLY_ARB_SCANNER", "ACC_POLY_ARB_SCANNER")
    assert result["recovered_capital_eur"] == 800.0


def test_recover_capital_publishes_bus_event(manager):
    store = PolyDataStore(base_path=manager.base_path)
    _create_paper_account(manager)
    manager.recover_capital("POLY_ARB_SCANNER", "ACC_POLY_ARB_SCANNER")
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "account:live_closed" in topics


def test_recover_capital_audits_event(manager):
    _create_paper_account(manager)
    manager.recover_capital("POLY_ARB_SCANNER", "ACC_POLY_ARB_SCANNER")
    audit = PolyAuditLog(base_path=manager.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "account:live_closed" in topics


def test_recover_capital_noop_if_account_not_found(manager):
    """Recovering a non-existent account does not crash."""
    result = manager.recover_capital("POLY_GHOST", "ACC_POLY_GHOST")
    assert result["status"] == "not_found"
    assert result["recovered_capital_eur"] == 0.0


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------

def test_run_once_processes_promotion_approved(manager):
    _publish_promotion_approved(manager, _make_promotion_payload())
    result = manager.run_once()
    assert len(result["created"]) == 1
    assert result["created"][0]["strategy"] == "POLY_ARB_SCANNER"


def test_run_once_acks_promotion_event(manager):
    """After run_once, re-polling should return no new promotion events."""
    _publish_promotion_approved(manager, _make_promotion_payload())
    manager.run_once()
    events = manager.bus.poll(CONSUMER_ID, topics=["promotion:approved"])
    assert len(events) == 0


def test_run_once_processes_stop_strategy_kill_switch(manager):
    _create_paper_account(manager)
    _publish_kill_switch_stop(manager, "POLY_ARB_SCANNER", "ACC_POLY_ARB_SCANNER")
    result = manager.run_once()
    assert len(result["recovered"]) == 1
    assert result["recovered"][0]["strategy"] == "POLY_ARB_SCANNER"


def test_run_once_ignores_non_stop_kill_switch_actions(manager):
    """pause_strategy kill switch events are acked but do not trigger recovery."""
    _create_paper_account(manager)
    _publish_kill_switch_pause(manager, "POLY_ARB_SCANNER", "ACC_POLY_ARB_SCANNER")
    result = manager.run_once()
    assert len(result["recovered"]) == 0
    # Account should still be loadable (not archived)
    account = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", manager.base_path)
    assert account is not None


def test_run_once_acks_kill_switch_event(manager):
    """After run_once, re-polling kill_switch events returns nothing."""
    _create_paper_account(manager)
    _publish_kill_switch_stop(manager, "POLY_ARB_SCANNER", "ACC_POLY_ARB_SCANNER")
    manager.run_once()
    events = manager.bus.poll(CONSUMER_ID, topics=["risk:kill_switch"])
    assert len(events) == 0


def test_run_once_returns_created_and_recovered_keys(manager):
    result = manager.run_once()
    assert "created" in result
    assert "recovered" in result


def test_run_once_no_events_returns_empty_lists(manager):
    result = manager.run_once()
    assert result["created"] == []
    assert result["recovered"] == []
