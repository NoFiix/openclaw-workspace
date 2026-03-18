"""
Tests for POLY_RISK_GUARDIAN (POLY-022).

Key acceptance criteria from ticket:
- 6 positions per strategy → blocked
- 40% strategy capital committed → blocked
- exposure 81% → blocked
"""

import pytest
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from risk.poly_risk_guardian import (
    PolyRiskGuardian,
    MAX_POSITIONS_PER_STRATEGY,
    MAX_CAPITAL_USAGE_PER_STRATEGY,
    MAX_EXPOSURE_PCT,
    MAX_CATEGORY_PCT,
    CONSUMER_ID,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def guardian(tmp_path):
    return PolyRiskGuardian(base_path=str(tmp_path))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_n_positions(guardian, n, size_eur=10.0, category="bundle_arb", strategy="STRAT_A"):
    """Add n positions for the SAME strategy (tests per-strategy limit)."""
    for i in range(n):
        guardian.add_position(
            strategy=strategy,
            market_id=f"0x{i:04x}",
            size_eur=size_eur,
            category=category,
        )


# ---------------------------------------------------------------------------
# Ticket acceptance criteria
# ---------------------------------------------------------------------------

def test_check_blocked_when_max_positions_per_strategy_reached(guardian):
    """6 existing positions for STRAT_A → 7th trade blocked."""
    _add_n_positions(guardian, MAX_POSITIONS_PER_STRATEGY, size_eur=10.0, strategy="STRAT_A")
    result = guardian.check(10.0, "bundle_arb", total_capital_eur=10_000.0,
                            strategy="STRAT_A", strategy_capital=1_000.0)
    assert result["allowed"] is False
    assert result["blocked_by"] == "strategy_position_limit"


def test_check_allowed_other_strategy_unaffected(guardian):
    """6 positions for STRAT_A does not block STRAT_B."""
    _add_n_positions(guardian, MAX_POSITIONS_PER_STRATEGY, size_eur=10.0, strategy="STRAT_A")
    result = guardian.check(10.0, "bundle_arb", total_capital_eur=10_000.0,
                            strategy="STRAT_B", strategy_capital=1_000.0)
    assert result["checks"]["positions_ok"] is True


def test_check_blocked_when_exposure_exceeds_limit(guardian):
    """Proposed trade pushes exposure to 81% → blocked (exposure_ok=False)."""
    total = 1_000.0
    # Add existing exposure: 70% = 700€
    guardian.add_position("STRAT_A", "0xaaa", 700.0, "bundle_arb")
    # Propose a trade of 115€ → total 815€ / 1000€ = 81.5% > 80%
    result = guardian.check(115.0, "weather_arb", total_capital_eur=total,
                            strategy="STRAT_B", strategy_capital=1_000.0)
    assert result["allowed"] is False
    assert result["blocked_by"] == "max_exposure"


# ---------------------------------------------------------------------------
# Position count checks
# ---------------------------------------------------------------------------

def test_check_allowed_with_zero_positions(guardian):
    result = guardian.check(50.0, "bundle_arb", total_capital_eur=1_000.0,
                            strategy="STRAT_A", strategy_capital=1_000.0)
    assert result["allowed"] is True


def test_check_allowed_with_five_positions(guardian):
    """5 existing positions for same strategy → 6th trade allowed (limit is 6)."""
    _add_n_positions(guardian, MAX_POSITIONS_PER_STRATEGY - 1, size_eur=5.0, strategy="STRAT_A")
    result = guardian.check(5.0, "bundle_arb", total_capital_eur=10_000.0,
                            strategy="STRAT_A", strategy_capital=10_000.0)
    assert result["checks"]["positions_ok"] is True


def test_check_blocked_at_exactly_max_positions_per_strategy(guardian):
    _add_n_positions(guardian, MAX_POSITIONS_PER_STRATEGY, size_eur=5.0, strategy="STRAT_A")
    result = guardian.check(5.0, "bundle_arb", total_capital_eur=10_000.0,
                            strategy="STRAT_A", strategy_capital=10_000.0)
    assert result["checks"]["positions_ok"] is False


def test_current_positions_count_in_result(guardian):
    _add_n_positions(guardian, 3, strategy="STRAT_A")
    result = guardian.check(10.0, "bundle_arb", total_capital_eur=10_000.0,
                            strategy="STRAT_A", strategy_capital=10_000.0)
    assert result["current_positions"] == 3
    assert result["strategy_positions"] == 3


# ---------------------------------------------------------------------------
# Exposure checks
# ---------------------------------------------------------------------------

def test_check_allowed_when_exposure_within_limit(guardian):
    """50% exposure → allowed."""
    total = 1_000.0
    guardian.add_position("STRAT_A", "0xaaa", 500.0, "bundle_arb")
    result = guardian.check(0.01, "weather_arb", total_capital_eur=total,
                            strategy="STRAT_B", strategy_capital=1_000.0)
    assert result["checks"]["exposure_ok"] is True


def test_check_blocked_exactly_above_exposure_limit(guardian):
    """Exposure would reach 80.01% → blocked."""
    total = 1_000.0
    guardian.add_position("STRAT_A", "0xaaa", 700.0, "bundle_arb")
    result = guardian.check(101.0, "weather_arb", total_capital_eur=total,
                            strategy="STRAT_B", strategy_capital=1_000.0)
    assert result["checks"]["exposure_ok"] is False


def test_check_allowed_at_exactly_exposure_limit(guardian):
    """Exactly 80% exposure → allowed (≤ limit)."""
    total = 1_000.0
    guardian.add_position("STRAT_A", "0xaaa", 700.0, "bundle_arb")
    result = guardian.check(100.0, "weather_arb", total_capital_eur=total,
                            strategy="STRAT_B", strategy_capital=1_000.0)
    assert result["checks"]["exposure_ok"] is True


def test_exposure_pct_in_result(guardian):
    guardian.add_position("STRAT_A", "0xaaa", 300.0, "bundle_arb")
    result = guardian.check(0.0, "weather_arb", total_capital_eur=1_000.0,
                            strategy="STRAT_B", strategy_capital=1_000.0)
    assert abs(result["current_exposure_pct"] - 0.30) < 1e-4


def test_proposed_size_in_result(guardian):
    result = guardian.check(42.0, "bundle_arb", total_capital_eur=1_000.0,
                            strategy="STRAT_A", strategy_capital=1_000.0)
    assert result["proposed_size_eur"] == 42.0


def test_total_capital_in_result(guardian):
    result = guardian.check(10.0, "bundle_arb", total_capital_eur=2_000.0,
                            strategy="STRAT_A", strategy_capital=2_000.0)
    assert result["total_capital_eur"] == 2_000.0


# ---------------------------------------------------------------------------
# Category concentration checks (anti-correlation)
# ---------------------------------------------------------------------------

def test_check_blocked_by_category_concentration(guardian):
    """Category exposure > 40% → blocked."""
    total = 1_000.0
    guardian.add_position("STRAT_A", "0xaaa", 350.0, "bundle_arb")
    result = guardian.check(60.0, "bundle_arb", total_capital_eur=total,
                            strategy="STRAT_B", strategy_capital=1_000.0)
    assert result["checks"]["category_ok"] is False
    assert result["blocked_by"] == "max_category_concentration"


def test_check_allowed_at_exactly_category_limit(guardian):
    """Exactly 40% in one category → allowed (≤ limit)."""
    total = 1_000.0
    guardian.add_position("STRAT_A", "0xaaa", 350.0, "bundle_arb")
    result = guardian.check(50.0, "bundle_arb", total_capital_eur=total,
                            strategy="STRAT_B", strategy_capital=1_000.0)
    assert result["checks"]["category_ok"] is True


def test_different_category_not_counted(guardian):
    """Exposure in a different category does not affect proposed category check."""
    total = 1_000.0
    guardian.add_position("STRAT_A", "0xaaa", 350.0, "weather_arb")
    result = guardian.check(100.0, "bundle_arb", total_capital_eur=total,
                            strategy="STRAT_B", strategy_capital=1_000.0)
    assert result["checks"]["category_ok"] is True


# ---------------------------------------------------------------------------
# Priority order of blocked_by
# ---------------------------------------------------------------------------

def test_positions_blocked_before_capital(guardian):
    """Position count check has priority over capital usage check."""
    _add_n_positions(guardian, MAX_POSITIONS_PER_STRATEGY, size_eur=5.0, strategy="STRAT_A")
    result = guardian.check(10_000.0, "bundle_arb", total_capital_eur=100_000.0,
                            strategy="STRAT_A", strategy_capital=100_000.0)
    assert result["blocked_by"] == "strategy_position_limit"


def test_capital_blocked_before_exposure(guardian):
    """Strategy capital check has priority over total exposure check."""
    # 1 position using 350€ of 1000€ strategy capital (35%)
    guardian.add_position("STRAT_A", "0xaaa", 350.0, "bundle_arb")
    # Propose 100€ → committed 450/1000 = 45% > 40% strategy limit
    result = guardian.check(100.0, "bundle_arb", total_capital_eur=10_000.0,
                            strategy="STRAT_A", strategy_capital=1_000.0)
    assert result["blocked_by"] == "strategy_capital_limit"


def test_exposure_blocked_before_category(guardian):
    """Exposure check has priority over category check when both fail."""
    total = 100.0
    guardian.add_position("STRAT_A", "0xaaa", 89.0, "bundle_arb")
    result = guardian.check(20.0, "bundle_arb", total_capital_eur=total,
                            strategy="STRAT_B", strategy_capital=10_000.0)
    assert result["blocked_by"] == "max_exposure"


# ---------------------------------------------------------------------------
# add_position and close_position
# ---------------------------------------------------------------------------

def test_add_position_increases_count(guardian):
    guardian.add_position("STRAT_A", "0xaaa", 50.0, "bundle_arb")
    state = guardian.get_state()
    assert len(state["open_positions"]) == 1


def test_add_multiple_positions(guardian):
    _add_n_positions(guardian, 3)
    state = guardian.get_state()
    assert len(state["open_positions"]) == 3


def test_close_position_decreases_count(guardian):
    guardian.add_position("STRAT_A", "0xaaa", 50.0, "bundle_arb")
    guardian.close_position("STRAT_A", "0xaaa")
    state = guardian.get_state()
    assert len(state["open_positions"]) == 0


def test_close_position_removes_correct_entry(guardian):
    """Closing one position does not affect others."""
    guardian.add_position("STRAT_A", "0xaaa", 50.0, "bundle_arb")
    guardian.add_position("STRAT_B", "0xbbb", 30.0, "weather_arb")
    guardian.close_position("STRAT_A", "0xaaa")
    state = guardian.get_state()
    assert len(state["open_positions"]) == 1
    assert state["open_positions"][0]["strategy"] == "STRAT_B"


def test_close_position_unknown_is_noop(guardian):
    """Closing a non-existent position does not crash."""
    guardian.close_position("STRAT_GHOST", "0xdead")
    state = guardian.get_state()
    assert len(state["open_positions"]) == 0


def test_check_after_close_reflects_updated_state(guardian):
    """After closing a position, exposure check reflects the lower exposure."""
    total = 1_000.0
    guardian.add_position("STRAT_A", "0xaaa", 800.0, "bundle_arb")
    result_before = guardian.check(1.0, "weather_arb", total_capital_eur=total,
                                   strategy="STRAT_B", strategy_capital=1_000.0)
    assert result_before["checks"]["exposure_ok"] is False
    guardian.close_position("STRAT_A", "0xaaa")
    result_after = guardian.check(50.0, "weather_arb", total_capital_eur=total,
                                  strategy="STRAT_B", strategy_capital=1_000.0)
    assert result_after["checks"]["exposure_ok"] is True


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def test_state_persisted_after_add(guardian):
    store = PolyDataStore(base_path=guardian.store.base_path)
    guardian.add_position("STRAT_A", "0xaaa", 50.0, "bundle_arb")
    state = store.read_json("risk/portfolio_state.json")
    assert len(state["open_positions"]) == 1


def test_state_persisted_after_close(guardian):
    store = PolyDataStore(base_path=guardian.store.base_path)
    guardian.add_position("STRAT_A", "0xaaa", 50.0, "bundle_arb")
    guardian.close_position("STRAT_A", "0xaaa")
    state = store.read_json("risk/portfolio_state.json")
    assert len(state["open_positions"]) == 0


def test_get_state_returns_snapshot(guardian):
    guardian.add_position("STRAT_A", "0xaaa", 50.0, "bundle_arb")
    state = guardian.get_state()
    assert "open_positions" in state
    assert len(state["open_positions"]) == 1


# ---------------------------------------------------------------------------
# Bus and audit integration
# ---------------------------------------------------------------------------

def test_bus_event_published_on_check(guardian):
    store = PolyDataStore(base_path=guardian.store.base_path)
    guardian.check(50.0, "bundle_arb", total_capital_eur=1_000.0,
                   strategy="STRAT_A", strategy_capital=1_000.0)
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "risk:portfolio_check" in topics


def test_bus_event_producer(guardian):
    store = PolyDataStore(base_path=guardian.store.base_path)
    guardian.check(50.0, "bundle_arb", total_capital_eur=1_000.0,
                   strategy="STRAT_A", strategy_capital=1_000.0)
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "risk:portfolio_check")
    assert evt["producer"] == CONSUMER_ID


def test_audit_logged_on_check(guardian):
    guardian.check(50.0, "bundle_arb", total_capital_eur=1_000.0,
                   strategy="STRAT_A", strategy_capital=1_000.0)
    audit = PolyAuditLog(base_path=guardian.store.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "risk:portfolio_check" in topics


def test_check_result_has_all_required_fields(guardian):
    result = guardian.check(50.0, "bundle_arb", total_capital_eur=1_000.0,
                            strategy="STRAT_A", strategy_capital=1_000.0)
    for field in ("allowed", "blocked_by", "checks", "current_positions",
                  "strategy_positions", "current_exposure_eur", "current_exposure_pct",
                  "proposed_size_eur", "total_capital_eur"):
        assert field in result


def test_checks_dict_has_all_four_keys(guardian):
    result = guardian.check(50.0, "bundle_arb", total_capital_eur=1_000.0,
                            strategy="STRAT_A", strategy_capital=1_000.0)
    assert set(result["checks"].keys()) == {"exposure_ok", "positions_ok", "strategy_capital_ok", "category_ok"}


# ---------------------------------------------------------------------------
# Per-strategy capital usage
# ---------------------------------------------------------------------------

def test_strategy_capital_usage_blocked(guardian):
    """Committed capital > 40% of strategy capital → blocked."""
    guardian.add_position("STRAT_A", "0xaaa", 350.0, "bundle_arb")
    # 350 + 60 = 410 / 1000 = 41% > 40%
    result = guardian.check(60.0, "bundle_arb", total_capital_eur=10_000.0,
                            strategy="STRAT_A", strategy_capital=1_000.0)
    assert result["checks"]["strategy_capital_ok"] is False
    assert result["blocked_by"] == "strategy_capital_limit"


def test_strategy_capital_usage_allowed(guardian):
    """Committed capital ≤ 40% → allowed."""
    guardian.add_position("STRAT_A", "0xaaa", 350.0, "bundle_arb")
    # 350 + 50 = 400 / 1000 = 40% == limit → allowed
    result = guardian.check(50.0, "bundle_arb", total_capital_eur=10_000.0,
                            strategy="STRAT_A", strategy_capital=1_000.0)
    assert result["checks"]["strategy_capital_ok"] is True


# ---------------------------------------------------------------------------
# close_positions_for_market
# ---------------------------------------------------------------------------

def test_close_positions_for_market(guardian):
    """Closing a resolved market removes all positions on it."""
    guardian.add_position("STRAT_A", "0xaaa", 50.0, "bundle_arb")
    guardian.add_position("STRAT_B", "0xaaa", 30.0, "weather_arb")
    guardian.add_position("STRAT_A", "0xbbb", 20.0, "bundle_arb")
    closed = guardian.close_positions_for_market("0xaaa")
    assert closed == 2
    state = guardian.get_state()
    assert len(state["open_positions"]) == 1
    assert state["open_positions"][0]["market_id"] == "0xbbb"


def test_close_positions_for_unknown_market_is_noop(guardian):
    closed = guardian.close_positions_for_market("0xdead")
    assert closed == 0


# ---------------------------------------------------------------------------
# add_position dedup
# ---------------------------------------------------------------------------

def test_add_position_dedup_merges_size(guardian):
    """Adding same (strategy, market_id) merges size_eur."""
    guardian.add_position("STRAT_A", "0xaaa", 50.0, "bundle_arb")
    guardian.add_position("STRAT_A", "0xaaa", 30.0, "bundle_arb")
    state = guardian.get_state()
    assert len(state["open_positions"]) == 1
    assert state["open_positions"][0]["size_eur"] == 80.0
