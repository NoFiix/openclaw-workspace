"""
Tests for POLY_STRATEGY_ACCOUNT (POLY-015).

Ticket acceptance: create, trade +50€, trade -100€ → capital/pnl/drawdown verified.
"""

import os
import pytest

from core.poly_strategy_account import (
    DAILY_DRAWDOWN_LIMIT_PCT,
    TOTAL_DRAWDOWN_LIMIT_PCT,
    PolyStrategyAccount,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def account(tmp_path):
    return PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))


@pytest.fixture
def account_after_positive(tmp_path):
    """Account after +50€ trade."""
    acc = PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    acc.record_trade(50.0)
    return acc


@pytest.fixture
def account_after_both(tmp_path):
    """Account after +50€ then -100€ trade."""
    acc = PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    acc.record_trade(50.0)
    acc.record_trade(-100.0)
    return acc


# ---------------------------------------------------------------------------
# Creation tests
# ---------------------------------------------------------------------------

def test_create_returns_instance(account):
    assert account is not None


def test_create_account_id_format(account):
    assert account.account_id == "ACC_POLY_ARB_SCANNER"


def test_create_initial_capital(account):
    d = account.data
    assert d["capital"]["initial"] == 1000.0
    assert d["capital"]["current"] == 1000.0
    assert d["capital"]["available"] == 1000.0


def test_create_zero_pnl(account):
    pnl = account.data["pnl"]
    assert pnl["total"] == 0.0
    assert pnl["daily"] == 0.0
    assert pnl["session"] == 0.0


def test_create_zero_drawdown(account):
    dd = account.data["drawdown"]
    assert dd["high_water_mark"] == 1000.0
    assert dd["current_drawdown_pct"] == 0.0
    assert dd["max_drawdown_pct"] == 0.0
    assert dd["daily_pnl_pct"] == 0.0


def test_create_status_paper_testing(account):
    assert account.status == "paper_testing"
    assert account.data["status_history"][0]["status"] == "paper_testing"


def test_create_limits_set(account):
    limits = account.data["limits"]
    assert limits["daily_drawdown_limit_pct"] == DAILY_DRAWDOWN_LIMIT_PCT
    assert limits["total_drawdown_limit_pct"] == TOTAL_DRAWDOWN_LIMIT_PCT


def test_create_duplicate_raises(tmp_path):
    PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    with pytest.raises(ValueError, match="already exists"):
        PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))


def test_create_saves_file(tmp_path):
    PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    expected = tmp_path / "accounts" / "ACC_POLY_ARB_SCANNER.json"
    assert expected.exists()


# ---------------------------------------------------------------------------
# Trade +50€ tests
# ---------------------------------------------------------------------------

def test_trade_positive_updates_capital(account_after_positive):
    assert account_after_positive.data["capital"]["current"] == 1050.0


def test_trade_positive_updates_available(account_after_positive):
    assert account_after_positive.data["capital"]["available"] == 1050.0


def test_trade_positive_updates_total_pnl(account_after_positive):
    assert account_after_positive.data["pnl"]["total"] == 50.0


def test_trade_positive_updates_daily_pnl(account_after_positive):
    assert account_after_positive.data["pnl"]["daily"] == 50.0


def test_trade_positive_raises_hwm(account_after_positive):
    assert account_after_positive.data["drawdown"]["high_water_mark"] == 1050.0


def test_trade_positive_no_drawdown(account_after_positive):
    assert account_after_positive.data["drawdown"]["current_drawdown_pct"] == 0.0


def test_trade_increments_trade_count(account_after_positive):
    assert account_after_positive.data["performance"]["total_trades"] == 1


def test_trade_sets_last_trade_at(account_after_positive):
    assert account_after_positive.data["performance"]["last_trade_at"] is not None


# ---------------------------------------------------------------------------
# Trade -100€ tests (after +50€, so net -50€)
# ---------------------------------------------------------------------------

def test_trade_negative_updates_capital(account_after_both):
    assert account_after_both.data["capital"]["current"] == 950.0


def test_trade_negative_total_pnl(account_after_both):
    assert account_after_both.data["pnl"]["total"] == -50.0


def test_trade_negative_daily_pnl(account_after_both):
    assert account_after_both.data["pnl"]["daily"] == -50.0


def test_trade_negative_current_drawdown(account_after_both):
    # HWM = 1050, current = 950 → (950 - 1050) / 1050 * 100 ≈ -9.52%
    dd = account_after_both.data["drawdown"]["current_drawdown_pct"]
    expected = (950.0 - 1050.0) / 1050.0 * 100.0
    assert abs(dd - expected) < 0.01


def test_trade_negative_max_drawdown(account_after_both):
    # max_drawdown_pct should equal current_drawdown_pct (worst so far)
    d = account_after_both.data["drawdown"]
    assert d["max_drawdown_pct"] == d["current_drawdown_pct"]
    assert d["max_drawdown_pct"] < 0


def test_trade_negative_daily_pnl_pct(account_after_both):
    # daily_pnl = -50, initial = 1000 → -5.0%
    pct = account_after_both.data["drawdown"]["daily_pnl_pct"]
    assert abs(pct - (-5.0)) < 0.001


def test_trade_count_two(account_after_both):
    assert account_after_both.data["performance"]["total_trades"] == 2


def test_hwm_stays_at_peak(account_after_both):
    # HWM must not decrease even when capital falls
    assert account_after_both.data["drawdown"]["high_water_mark"] == 1050.0


# ---------------------------------------------------------------------------
# Status tests
# ---------------------------------------------------------------------------

def test_update_status_valid(account):
    d = account.update_status("paused")
    assert d["status"] == "paused"
    assert account.status == "paused"


def test_update_status_appends_history(account):
    account.update_status("paused")
    history = account.data["status_history"]
    assert len(history) == 2
    assert history[-1]["status"] == "paused"


def test_update_status_invalid_raises(account):
    with pytest.raises(ValueError, match="Invalid status"):
        account.update_status("unknown_status")


def test_update_status_stopped_archives(tmp_path):
    acc = PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    acc.update_status("stopped")
    original = tmp_path / "accounts" / "ACC_POLY_ARB_SCANNER.json"
    archive_dir = tmp_path / "accounts" / "archive"
    archived_files = list(archive_dir.iterdir())
    assert not original.exists()
    assert len(archived_files) == 1
    assert "ACC_POLY_ARB_SCANNER" in archived_files[0].name


# ---------------------------------------------------------------------------
# Reset daily tests
# ---------------------------------------------------------------------------

def test_reset_daily_clears_daily_pnl(tmp_path):
    acc = PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    acc.record_trade(50.0)
    assert acc.data["pnl"]["daily"] == 50.0
    acc.reset_daily()
    assert acc.data["pnl"]["daily"] == 0.0


def test_reset_daily_clears_daily_pct(tmp_path):
    acc = PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    acc.record_trade(-100.0)
    assert acc.data["drawdown"]["daily_pnl_pct"] < 0
    acc.reset_daily()
    assert acc.data["drawdown"]["daily_pnl_pct"] == 0.0


def test_reset_daily_does_not_affect_total_pnl(tmp_path):
    acc = PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    acc.record_trade(50.0)
    acc.reset_daily()
    assert acc.data["pnl"]["total"] == 50.0


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

def test_load_after_create(tmp_path):
    acc = PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    loaded = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", base_path=str(tmp_path))
    assert loaded.account_id == acc.account_id
    assert loaded.data["capital"]["initial"] == 1000.0


def test_load_nonexistent_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        PolyStrategyAccount.load("ACC_POLY_GHOST", base_path=str(tmp_path))


def test_persistence_after_trade(tmp_path):
    acc = PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    acc.record_trade(50.0)
    acc.record_trade(-100.0)

    loaded = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", base_path=str(tmp_path))
    assert loaded.data["capital"]["current"] == 950.0
    assert loaded.data["pnl"]["total"] == -50.0
    assert loaded.data["performance"]["total_trades"] == 2


def test_persistence_after_status_change(tmp_path):
    acc = PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    acc.update_status("paused")

    loaded = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", base_path=str(tmp_path))
    assert loaded.status == "paused"
    assert len(loaded.data["status_history"]) == 2


# ---------------------------------------------------------------------------
# Integration / audit log tests
# ---------------------------------------------------------------------------

def test_audit_log_created(tmp_path):
    PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    from core.poly_audit_log import PolyAuditLog
    audit = PolyAuditLog(base_path=str(tmp_path))
    topics = [e["topic"] for e in audit.read_events()]
    assert "account:created" in topics


def test_audit_log_trade(tmp_path):
    acc = PolyStrategyAccount.create("POLY_ARB_SCANNER", "polymarket", base_path=str(tmp_path))
    acc.record_trade(50.0)
    from core.poly_audit_log import PolyAuditLog
    audit = PolyAuditLog(base_path=str(tmp_path))
    topics = [e["topic"] for e in audit.read_events()]
    assert "account:trade_recorded" in topics


def test_custom_initial_capital(tmp_path):
    acc = PolyStrategyAccount.create("POLY_SMALL", "polymarket",
                                     base_path=str(tmp_path), initial_capital=500.0)
    assert acc.data["capital"]["initial"] == 500.0
    assert acc.data["capital"]["current"] == 500.0
    assert acc.data["drawdown"]["high_water_mark"] == 500.0
