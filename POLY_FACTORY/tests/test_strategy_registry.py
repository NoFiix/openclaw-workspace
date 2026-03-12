"""
Tests for POLY_STRATEGY_REGISTRY (POLY-014).
"""

import pytest

from core.poly_strategy_registry import (
    VALID_STATUSES,
    STATUS_TO_LIFECYCLE,
    PolyStrategyRegistry,
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def registry(tmp_path):
    return PolyStrategyRegistry(base_path=str(tmp_path))


def _register(reg, name="POLY_ARB_SCANNER", **kwargs):
    defaults = dict(
        category="arbitrage",
        platform="polymarket",
        parameters={"threshold": 0.97},
        notes="test strategy",
    )
    defaults.update(kwargs)
    return reg.register(name, **defaults)


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

def test_register_creates_entry(registry):
    _register(registry)
    assert registry.get("POLY_ARB_SCANNER") is not None


def test_register_generates_strategy_id(registry):
    entry = _register(registry)
    assert entry["strategy_id"] == "STRAT_001"


def test_register_second_increments_id(registry):
    _register(registry, "POLY_STRAT_A")
    entry2 = _register(registry, "POLY_STRAT_B")
    assert entry2["strategy_id"] == "STRAT_002"


def test_register_duplicate_raises(registry):
    _register(registry)
    with pytest.raises(ValueError, match="already registered"):
        _register(registry)


def test_register_sets_scouted_lifecycle(registry):
    entry = _register(registry)
    lc = entry["lifecycle"]
    assert lc["scouted"] is not None
    # All other lifecycle fields should be null
    for field in ("backtested", "paper_started", "paper_evaluated",
                  "promoted_live", "paused", "stopped", "reactivated"):
        assert lc[field] is None, f"Expected {field} to be null"


def test_register_initial_parameter_history(registry):
    entry = _register(registry, parameters={"threshold": 0.97})
    assert len(entry["parameter_history"]) == 1
    assert entry["parameter_history"][0]["version"] == "1.0"
    assert entry["parameter_history"][0]["params"] == {"threshold": 0.97}


def test_register_initial_status_is_scouted(registry):
    entry = _register(registry)
    assert entry["status"] == "scouted"


def test_register_initial_version_is_1_0(registry):
    entry = _register(registry)
    assert entry["version"] == "1.0"


# ---------------------------------------------------------------------------
# Status tests
# ---------------------------------------------------------------------------

def test_update_status_valid(registry):
    _register(registry)
    entry = registry.update_status("POLY_ARB_SCANNER", "paper_testing")
    assert entry["status"] == "paper_testing"


def test_update_status_sets_lifecycle_field(registry):
    _register(registry)
    entry = registry.update_status("POLY_ARB_SCANNER", "paper_testing")
    assert entry["lifecycle"]["paper_started"] is not None


def test_update_status_unknown_name_raises(registry):
    with pytest.raises(ValueError, match="not found"):
        registry.update_status("POLY_NONEXISTENT", "live")


def test_update_status_invalid_status_raises(registry):
    _register(registry)
    with pytest.raises(ValueError, match="Invalid status"):
        registry.update_status("POLY_ARB_SCANNER", "flying")


def test_update_status_lifecycle_not_overwritten(registry):
    _register(registry)
    entry1 = registry.update_status("POLY_ARB_SCANNER", "paper_testing")
    first_ts = entry1["lifecycle"]["paper_started"]
    # Setting same status again should not overwrite the timestamp
    entry2 = registry.update_status("POLY_ARB_SCANNER", "paper_testing")
    assert entry2["lifecycle"]["paper_started"] == first_ts


# ---------------------------------------------------------------------------
# Parameter tests
# ---------------------------------------------------------------------------

def test_update_parameters_changes_params(registry):
    _register(registry, parameters={"threshold": 0.97})
    entry = registry.update_parameters("POLY_ARB_SCANNER", {"threshold": 0.95})
    assert entry["parameters"] == {"threshold": 0.95}


def test_update_parameters_appends_history(registry):
    _register(registry)
    entry = registry.update_parameters("POLY_ARB_SCANNER", {"threshold": 0.95})
    assert len(entry["parameter_history"]) == 2


def test_update_parameters_auto_increments_version(registry):
    _register(registry)
    entry = registry.update_parameters("POLY_ARB_SCANNER", {"x": 1})
    assert entry["version"] == "1.1"


def test_update_parameters_second_increment(registry):
    _register(registry)
    registry.update_parameters("POLY_ARB_SCANNER", {"x": 1})   # 1.1
    entry = registry.update_parameters("POLY_ARB_SCANNER", {"x": 2})  # 1.2
    assert entry["version"] == "1.2"


def test_update_parameters_custom_version(registry):
    _register(registry)
    entry = registry.update_parameters("POLY_ARB_SCANNER", {"x": 1}, new_version="2.0")
    assert entry["version"] == "2.0"
    assert entry["parameter_history"][-1]["version"] == "2.0"


def test_update_parameters_unknown_name_raises(registry):
    with pytest.raises(ValueError, match="not found"):
        registry.update_parameters("POLY_NONEXISTENT", {})


# ---------------------------------------------------------------------------
# Backtest / account ID tests
# ---------------------------------------------------------------------------

def test_add_backtest_id(registry):
    _register(registry)
    entry = registry.add_backtest_id("POLY_ARB_SCANNER", "BT_20260312_0001")
    assert "BT_20260312_0001" in entry["backtest_ids"]


def test_add_backtest_id_unknown_raises(registry):
    with pytest.raises(ValueError, match="not found"):
        registry.add_backtest_id("POLY_GHOST", "BT_001")


def test_add_account_id(registry):
    _register(registry)
    entry = registry.add_account_id("POLY_ARB_SCANNER", "ACC_POLY_ARB_SCANNER_v1")
    assert "ACC_POLY_ARB_SCANNER_v1" in entry["account_ids"]


def test_add_account_id_unknown_raises(registry):
    with pytest.raises(ValueError, match="not found"):
        registry.add_account_id("POLY_GHOST", "ACC_X")


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

def test_persistence_after_restart(tmp_path):
    reg1 = PolyStrategyRegistry(base_path=str(tmp_path))
    _register(reg1, parameters={"threshold": 0.97})
    reg1.update_status("POLY_ARB_SCANNER", "paper_testing")

    # Simulate restart
    reg2 = PolyStrategyRegistry(base_path=str(tmp_path))
    entry = reg2.get("POLY_ARB_SCANNER")
    assert entry is not None
    assert entry["status"] == "paper_testing"
    assert entry["parameters"] == {"threshold": 0.97}
    assert entry["lifecycle"]["paper_started"] is not None


def test_all_mutations_persisted(tmp_path):
    reg1 = PolyStrategyRegistry(base_path=str(tmp_path))
    _register(reg1, parameters={"a": 1})
    reg1.update_parameters("POLY_ARB_SCANNER", {"a": 2})
    reg1.update_status("POLY_ARB_SCANNER", "backtesting")
    reg1.add_backtest_id("POLY_ARB_SCANNER", "BT_001")
    reg1.add_account_id("POLY_ARB_SCANNER", "ACC_POLY_ARB_SCANNER_v1")

    reg2 = PolyStrategyRegistry(base_path=str(tmp_path))
    entry = reg2.get("POLY_ARB_SCANNER")
    assert entry["version"] == "1.1"
    assert entry["parameters"] == {"a": 2}
    assert entry["status"] == "backtesting"
    assert "BT_001" in entry["backtest_ids"]
    assert "ACC_POLY_ARB_SCANNER_v1" in entry["account_ids"]


def test_id_counter_restored_after_restart(tmp_path):
    reg1 = PolyStrategyRegistry(base_path=str(tmp_path))
    _register(reg1, "POLY_STRAT_A")
    _register(reg1, "POLY_STRAT_B")

    reg2 = PolyStrategyRegistry(base_path=str(tmp_path))
    entry = reg2.register("POLY_STRAT_C", "test", "polymarket", {})
    # Should be STRAT_003, not STRAT_001
    assert entry["strategy_id"] == "STRAT_003"


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def test_get_all_returns_all(registry):
    _register(registry, "POLY_STRAT_A")
    _register(registry, "POLY_STRAT_B")
    all_entries = registry.get_all()
    assert "POLY_STRAT_A" in all_entries
    assert "POLY_STRAT_B" in all_entries
    assert len(all_entries) == 2


def test_get_returns_none_for_unknown(registry):
    assert registry.get("POLY_GHOST") is None


def test_audit_log_entries(registry, tmp_path):
    reg = PolyStrategyRegistry(base_path=str(tmp_path))
    _register(reg)
    reg.update_status("POLY_ARB_SCANNER", "paper_testing")

    from core.poly_audit_log import PolyAuditLog
    audit = PolyAuditLog(base_path=str(tmp_path))
    events = audit.read_events()
    topics = [e["topic"] for e in events]
    assert "registry:strategy_registered" in topics
    assert "registry:status_updated" in topics


def test_get_returns_independent_copy(registry):
    """Mutating the returned dict does not affect the registry."""
    _register(registry, parameters={"x": 1})
    entry = registry.get("POLY_ARB_SCANNER")
    entry["parameters"]["x"] = 999
    assert registry.get("POLY_ARB_SCANNER")["parameters"]["x"] == 1
