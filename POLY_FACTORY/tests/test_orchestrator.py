"""
Tests for POLY_FACTORY_ORCHESTRATOR (POLY-035).

~40 tests covering:
- 7-filter chain (happy path + each rejection)
- Signal routing (validated / rejected)
- Kill switch lifecycle handling
- Eval score / promotion eligibility
- Promotion result handling
- Global risk status updates
- Cache updates from bus
- Nightly cycle
- Ack / state persistence
"""

import json
import os
import pytest
from datetime import datetime, timedelta, timezone

from core.poly_data_store import PolyDataStore
from core.poly_factory_orchestrator import (
    PolyFactoryOrchestrator,
    CONSUMER_ID,
    MIN_EXECUTABILITY_SCORE,
    MIN_SLIPPAGE_THRESHOLD,
    MAX_AMBIGUITY_SCORE,
    MIN_PAPER_TRADES,
    MIN_PAPER_DAYS,
    MIN_SCORE_FOR_PROMOTION,
    FILTER_NAMES,
)


# ---------------------------------------------------------------------------
# Constants used across tests
# ---------------------------------------------------------------------------

STRATEGY = "POLY_TEST_STRAT"
ACCOUNT_ID = f"ACC_{STRATEGY}"
MARKET_ID = "market-001"


# ---------------------------------------------------------------------------
# Mock classes
# ---------------------------------------------------------------------------

class MockKillSwitch:
    def __init__(self, allowed=True, reason=None):
        self._allowed = allowed
        self._reason = reason
        self.reset_daily_calls = []

    def check_pre_trade(self, strategy):
        return {
            "allowed": self._allowed,
            "level": "OK" if self._allowed else "PAUSE_DAILY",
            "reason": self._reason,
        }

    def reset_daily(self, strategy):
        self.reset_daily_calls.append(strategy)


class MockRiskGuardian:
    def __init__(self, allowed=True, blocked_by=None):
        self._allowed = allowed
        self._blocked_by = blocked_by

    def check(self, proposed_size_eur, proposed_category, total_capital_eur):
        return {
            "allowed": self._allowed,
            "blocked_by": self._blocked_by,
            "checks": {},
        }


class MockCapitalManager:
    def __init__(self, allowed=True, reason=None):
        self._allowed = allowed
        self._reason = reason

    def check_capital(self, account_id, size_eur):
        return {
            "allowed": self._allowed,
            "available_capital_eur": 1000.0 if self._allowed else 0.0,
            "required_eur": size_eur,
            "reason": self._reason,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_signal(
    market_id=MARKET_ID,
    strategy=STRATEGY,
    direction="BUY_YES",
    signal_type="momentum",
    confidence=0.70,
    suggested_size_eur=50.0,
) -> dict:
    return {
        "market_id": market_id,
        "strategy": strategy,
        "account_id": f"ACC_{strategy}",
        "platform": "polymarket",
        "direction": direction,
        "signal_type": signal_type,
        "confidence": confidence,
        "suggested_size_eur": suggested_size_eur,
    }


def _make_price(
    market_id=MARKET_ID,
    data_status="VALID",
    yes_ask=0.55,
    no_ask=0.45,
) -> dict:
    return {
        "market_id": market_id,
        "data_status": data_status,
        "yes_ask": yes_ask,
        "no_ask": no_ask,
    }


def _make_structure(
    market_id=MARKET_ID,
    executability_score=75,
    slippage_1k=0.005,
    depth_usd=10000.0,
) -> dict:
    return {
        "market_id": market_id,
        "executability_score": executability_score,
        "slippage_1k": slippage_1k,
        "depth_usd": depth_usd,
    }


def _make_resolution(market_id=MARKET_ID, ambiguity_score=2) -> dict:
    return {
        "market_id": market_id,
        "ambiguity_score": ambiguity_score,
    }


def _make_account(
    tmp_path,
    strategy=STRATEGY,
    capital=1000.0,
    total_trades=60,
    paper_days=20,
    daily_pnl=0.0,
    status="paper_testing",
) -> str:
    """Create a minimal account JSON file and return the account_id."""
    account_id = f"ACC_{strategy}"
    paper_started = (
        datetime.now(timezone.utc) - timedelta(days=paper_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    data = {
        "account_id": account_id,
        "strategy": strategy,
        "status": status,
        "platform": "polymarket",
        "capital": {
            "initial": 1000.0,
            "current": capital,
            "available": capital,
        },
        "pnl": {
            "total": 0.0,
            "daily": daily_pnl,
            "session": 0.0,
        },
        "drawdown": {
            "high_water_mark": 1000.0,
            "current_drawdown_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "daily_pnl_pct": 0.0,
        },
        "performance": {
            "total_trades": total_trades,
            "paper_started": paper_started,
            "last_trade_at": None,
        },
        "limits": {
            "daily_drawdown_limit_pct": -5.0,
            "total_drawdown_limit_pct": -30.0,
        },
        "status_history": [{"status": status, "timestamp": _now_str()}],
        "created_at": _now_str(),
        "updated_at": _now_str(),
    }

    store = PolyDataStore(base_path=str(tmp_path))
    store.write_json(f"accounts/{account_id}.json", data)
    return account_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def orchestrator(tmp_path):
    """Orchestrator with all mocks injected and caches pre-populated."""
    base = str(tmp_path)

    # Create account so filter 3 (sizing) can load it
    _make_account(tmp_path, STRATEGY, capital=1000.0, total_trades=60, paper_days=20)

    orch = PolyFactoryOrchestrator(
        base_path=base,
        kill_switch=MockKillSwitch(allowed=True),
        risk_guardian=MockRiskGuardian(allowed=True),
        capital_manager=MockCapitalManager(allowed=True),
    )

    # Pre-populate caches so signals pass all 7 filters by default
    orch._price_cache[MARKET_ID] = _make_price()
    orch._market_structure_cache[MARKET_ID] = _make_structure()
    orch._resolution_cache[MARKET_ID] = _make_resolution()

    return orch


# ---------------------------------------------------------------------------
# Filter chain tests
# ---------------------------------------------------------------------------

def test_signal_passes_all_7_filters(orchestrator):
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is True
    assert result["validated_size_eur"] is not None
    assert result["validated_size_eur"] > 0
    assert result["rejected_by"] is None


def test_filter_0_rejects_no_price_data(orchestrator):
    orchestrator._price_cache.pop(MARKET_ID, None)
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is False
    assert result["rejected_by"] == "data_quality"
    assert result["reason"] == "no_price_data"


def test_filter_0_rejects_suspect_data(orchestrator):
    orchestrator._price_cache[MARKET_ID] = _make_price(data_status="SUSPECT")
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is False
    assert result["rejected_by"] == "data_quality"
    assert result["reason"] == "data_suspect"


def test_filter_1_rejects_low_executability(orchestrator):
    orchestrator._market_structure_cache[MARKET_ID] = _make_structure(
        executability_score=MIN_EXECUTABILITY_SCORE - 1
    )
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is False
    assert result["rejected_by"] == "microstructure"


def test_filter_1_rejects_high_slippage(orchestrator):
    orchestrator._market_structure_cache[MARKET_ID] = _make_structure(
        slippage_1k=MIN_SLIPPAGE_THRESHOLD + 0.01
    )
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is False
    assert result["rejected_by"] == "microstructure"


def test_filter_1_rejects_no_structure(orchestrator):
    orchestrator._market_structure_cache.pop(MARKET_ID, None)
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is False
    assert result["rejected_by"] == "microstructure"
    assert result["reason"] == "no_structure_data"


def test_filter_2_rejects_high_ambiguity(orchestrator):
    orchestrator._resolution_cache[MARKET_ID] = _make_resolution(
        ambiguity_score=MAX_AMBIGUITY_SCORE  # >= threshold → reject
    )
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is False
    assert result["rejected_by"] == "resolution"
    assert result["reason"] == "high_ambiguity"


def test_filter_2_skipped_for_bundle_arb(orchestrator):
    """bundle_arb skips filter 2 even without a resolution cache entry."""
    orchestrator._resolution_cache.pop(MARKET_ID, None)
    signal = _make_signal(signal_type="bundle_arb")
    result = orchestrator._run_filter_chain(signal)
    # Should NOT fail on resolution — may fail later (sizing), but not resolution
    assert result["rejected_by"] != "resolution"


def test_filter_3_rejects_no_edge(orchestrator):
    # confidence <= yes_ask → kelly returns 0 → no edge
    orchestrator._price_cache[MARKET_ID] = _make_price(yes_ask=0.80, no_ask=0.20)
    signal = _make_signal(confidence=0.50, direction="BUY_YES")
    result = orchestrator._run_filter_chain(signal)
    assert result["passed"] is False
    assert result["rejected_by"] == "sizing"
    assert result["reason"] == "no_kelly_edge"


def test_filter_4_rejects_kill_switch_blocked(orchestrator):
    orchestrator.kill_switch = MockKillSwitch(allowed=False, reason="daily_drawdown_exceeded")
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is False
    assert result["rejected_by"] == "kill_switch"


def test_filter_5_rejects_risk_guardian_blocked(orchestrator):
    orchestrator.risk_guardian = MockRiskGuardian(allowed=False, blocked_by="max_positions")
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is False
    assert result["rejected_by"] == "risk_guardian"


def test_filter_6_rejects_insufficient_capital(orchestrator):
    orchestrator.capital_manager = MockCapitalManager(
        allowed=False, reason="insufficient_capital"
    )
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is False
    assert result["rejected_by"] == "capital_manager"


def test_filters_passed_list_in_result(orchestrator):
    result = orchestrator._run_filter_chain(_make_signal())
    assert result["passed"] is True
    assert result["filters_passed"] == FILTER_NAMES


# ---------------------------------------------------------------------------
# Signal routing
# ---------------------------------------------------------------------------

def test_valid_signal_published_as_trade_validated(orchestrator):
    orchestrator.bus.publish("trade:signal", STRATEGY, _make_signal())
    actions = orchestrator.run_once()
    validated = [a for a in actions if a["type"] == "signal_validated"]
    assert len(validated) == 1

    # Verify trade:validated was published on the bus
    events = orchestrator.bus.poll("TEST_CONSUMER", topics=["trade:validated"])
    assert len(events) == 1


def test_invalid_signal_not_published(orchestrator):
    orchestrator._price_cache.pop(MARKET_ID, None)
    orchestrator.bus.publish("trade:signal", STRATEGY, _make_signal())
    orchestrator.run_once()

    events = orchestrator.bus.poll("TEST_CONSUMER", topics=["trade:validated"])
    assert len(events) == 0


def test_trade_validated_payload_fields(orchestrator):
    orchestrator.bus.publish("trade:signal", STRATEGY, _make_signal())
    actions = orchestrator.run_once()
    validated = [a for a in actions if a["type"] == "signal_validated"]
    assert len(validated) == 1

    p = validated[0]["payload"]
    assert "strategy" in p
    assert "account_id" in p
    assert "market_id" in p
    assert "validated_size_eur" in p
    assert "filters_passed" in p
    assert "tranches" in p
    assert p["tranches"] is not None
    assert len(p["tranches"]) >= 1


def test_signal_audit_logged(orchestrator):
    """Audit log is written on a valid signal."""
    orchestrator.bus.publish("trade:signal", STRATEGY, _make_signal())
    orchestrator.run_once()
    # No exception = audit write succeeded (PolyAuditLog raises on I/O failure)


def test_rejected_signal_audit_logged(orchestrator):
    """Audit log is written on a rejected signal."""
    orchestrator._price_cache.pop(MARKET_ID, None)
    orchestrator.bus.publish("trade:signal", STRATEGY, _make_signal())
    orchestrator.run_once()
    # No exception = audit write succeeded


# ---------------------------------------------------------------------------
# Kill switch handling
# ---------------------------------------------------------------------------

def test_kill_switch_pause_updates_lifecycle(orchestrator):
    payload = {
        "action": "pause_strategy",
        "strategy": STRATEGY,
        "account_id": ACCOUNT_ID,
        "reason": "daily_drawdown_exceeded",
    }
    orchestrator.bus.publish("risk:kill_switch", "POLY_KILL_SWITCH", payload)
    orchestrator.run_once()
    assert orchestrator._lifecycle[STRATEGY]["lifecycle_phase"] == "paused"


def test_kill_switch_stop_updates_lifecycle_and_registry(orchestrator, tmp_path):
    # Register the strategy first so registry.update_status won't raise
    orchestrator.registry.register(
        name=STRATEGY,
        category="test",
        platform="polymarket",
        parameters={},
    )
    payload = {
        "action": "stop_strategy",
        "strategy": STRATEGY,
        "account_id": ACCOUNT_ID,
        "reason": "total_drawdown_exceeded",
    }
    orchestrator.bus.publish("risk:kill_switch", "POLY_KILL_SWITCH", payload)
    orchestrator.run_once()

    assert orchestrator._lifecycle[STRATEGY]["lifecycle_phase"] == "stopped"
    reg_entry = orchestrator.registry.get(STRATEGY)
    assert reg_entry["status"] == "stopped"


# ---------------------------------------------------------------------------
# Eval score / promotion
# ---------------------------------------------------------------------------

def test_eval_triggers_promotion_when_eligible(orchestrator, tmp_path):
    _make_account(tmp_path, STRATEGY, total_trades=60, paper_days=20)
    payload = {
        "strategy": STRATEGY,
        "score": 75,
        "verdict": "PROMOTE",
    }
    orchestrator.bus.publish("eval:score_updated", "POLY_EVALUATOR", payload)
    actions = orchestrator.run_once()

    handled = [a for a in actions if a["type"] == "eval_score_handled"]
    assert len(handled) == 1
    assert handled[0]["promotion_requested"] is True

    promo_events = orchestrator.bus.poll("TEST", topics=["promotion:request"])
    assert len(promo_events) == 1


def test_eval_no_promotion_below_min_score(orchestrator, tmp_path):
    _make_account(tmp_path, STRATEGY, total_trades=60, paper_days=20)
    payload = {"strategy": STRATEGY, "score": MIN_SCORE_FOR_PROMOTION - 1, "verdict": "OK"}
    orchestrator.bus.publish("eval:score_updated", "POLY_EVALUATOR", payload)
    actions = orchestrator.run_once()

    handled = [a for a in actions if a["type"] == "eval_score_handled"]
    assert handled[0]["promotion_requested"] is False

    promo_events = orchestrator.bus.poll("TEST2", topics=["promotion:request"])
    assert len(promo_events) == 0


def test_eval_no_promotion_insufficient_trades(orchestrator, tmp_path):
    _make_account(tmp_path, STRATEGY, total_trades=MIN_PAPER_TRADES - 1, paper_days=20)
    payload = {"strategy": STRATEGY, "score": 75, "verdict": "OK"}
    orchestrator.bus.publish("eval:score_updated", "POLY_EVALUATOR", payload)
    actions = orchestrator.run_once()

    handled = [a for a in actions if a["type"] == "eval_score_handled"]
    assert handled[0]["promotion_requested"] is False


def test_eval_no_promotion_insufficient_days(orchestrator, tmp_path):
    _make_account(tmp_path, STRATEGY, total_trades=60, paper_days=MIN_PAPER_DAYS - 1)
    payload = {"strategy": STRATEGY, "score": 75, "verdict": "OK"}
    orchestrator.bus.publish("eval:score_updated", "POLY_EVALUATOR", payload)
    actions = orchestrator.run_once()

    handled = [a for a in actions if a["type"] == "eval_score_handled"]
    assert handled[0]["promotion_requested"] is False


def test_eval_no_promotion_if_global_risk_not_normal(orchestrator, tmp_path):
    _make_account(tmp_path, STRATEGY, total_trades=60, paper_days=20)
    orchestrator._system_state["global_risk_status"] = "ALERTE"

    payload = {"strategy": STRATEGY, "score": 75, "verdict": "OK"}
    orchestrator.bus.publish("eval:score_updated", "POLY_EVALUATOR", payload)
    actions = orchestrator.run_once()

    handled = [a for a in actions if a["type"] == "eval_score_handled"]
    assert handled[0]["promotion_requested"] is False


def test_eval_no_promotion_if_already_requested(orchestrator, tmp_path):
    _make_account(tmp_path, STRATEGY, total_trades=60, paper_days=20)
    # Pre-mark promotion as already requested
    with orchestrator._lock:
        entry = orchestrator._get_lifecycle_entry(STRATEGY)
        entry["promotion_requested"] = True

    payload = {"strategy": STRATEGY, "score": 75, "verdict": "OK"}
    orchestrator.bus.publish("eval:score_updated", "POLY_EVALUATOR", payload)
    actions = orchestrator.run_once()

    handled = [a for a in actions if a["type"] == "eval_score_handled"]
    assert handled[0]["promotion_requested"] is False


def test_eval_no_promotion_for_retire_verdict(orchestrator, tmp_path):
    _make_account(tmp_path, STRATEGY, total_trades=60, paper_days=20)
    payload = {"strategy": STRATEGY, "score": 75, "verdict": "RETIRE"}
    orchestrator.bus.publish("eval:score_updated", "POLY_EVALUATOR", payload)
    actions = orchestrator.run_once()

    handled = [a for a in actions if a["type"] == "eval_score_handled"]
    assert handled[0]["promotion_requested"] is False


# ---------------------------------------------------------------------------
# Promotion result handling
# ---------------------------------------------------------------------------

def test_promotion_approved_updates_lifecycle(orchestrator):
    with orchestrator._lock:
        entry = orchestrator._get_lifecycle_entry(STRATEGY)
        entry["promotion_requested"] = True

    payload = {"strategy": STRATEGY}
    orchestrator.bus.publish("promotion:approved", "POLY_GATE", payload)
    orchestrator.run_once()

    assert orchestrator._lifecycle[STRATEGY]["lifecycle_phase"] == "awaiting_live"
    assert orchestrator._lifecycle[STRATEGY]["promotion_requested"] is False


def test_promotion_denied_clears_request_flag(orchestrator):
    with orchestrator._lock:
        entry = orchestrator._get_lifecycle_entry(STRATEGY)
        entry["promotion_requested"] = True

    payload = {"strategy": STRATEGY, "reason": "insufficient_backtest"}
    orchestrator.bus.publish("promotion:denied", "POLY_GATE", payload)
    orchestrator.run_once()

    assert orchestrator._lifecycle[STRATEGY]["promotion_requested"] is False


# ---------------------------------------------------------------------------
# Global risk
# ---------------------------------------------------------------------------

def test_global_risk_status_updated_in_system_state(orchestrator):
    orchestrator.bus.publish(
        "risk:global_status",
        "POLY_GLOBAL_RISK_GUARD",
        {"status": "ALERTE"},
    )
    orchestrator.run_once()
    assert orchestrator._system_state["global_risk_status"] == "ALERTE"


# ---------------------------------------------------------------------------
# Cache updates
# ---------------------------------------------------------------------------

def test_price_cache_updated_from_bus(orchestrator):
    new_price = _make_price(market_id="market-new", data_status="VALID", yes_ask=0.60)
    orchestrator.bus.publish("feed:price_update", "POLY_FEED", new_price)
    orchestrator.run_once()
    assert orchestrator._price_cache.get("market-new") == new_price


def test_resolution_cache_updated_from_bus(orchestrator):
    new_res = _make_resolution(market_id="market-new", ambiguity_score=1)
    orchestrator.bus.publish("signal:resolution_parsed", "POLY_ANALYST", new_res)
    orchestrator.run_once()
    assert orchestrator._resolution_cache.get("market-new") == new_res


# ---------------------------------------------------------------------------
# Nightly cycle
# ---------------------------------------------------------------------------

def test_nightly_resets_daily_on_accounts(orchestrator, tmp_path):
    # Create account with non-zero daily pnl
    _make_account(tmp_path, STRATEGY, daily_pnl=50.0)

    # Register the strategy in lifecycle so nightly iterates it
    with orchestrator._lock:
        orchestrator._lifecycle[STRATEGY] = {
            "lifecycle_phase": "paper",
            "promotion_requested": False,
        }

    orchestrator.run_nightly()

    from core.poly_strategy_account import PolyStrategyAccount
    account = PolyStrategyAccount.load(ACCOUNT_ID, str(tmp_path))
    assert account.data["pnl"]["daily"] == 0.0


def test_nightly_writes_cycle_log(orchestrator, tmp_path):
    orchestrator.run_nightly()

    store = PolyDataStore(base_path=str(tmp_path))
    log = store.read_json("orchestrator/cycle_log.json")
    assert isinstance(log, list)
    assert len(log) >= 1
    assert "cycle_completed_at" in log[-1]


def test_nightly_updates_last_nightly_run(orchestrator):
    assert orchestrator._system_state.get("last_nightly_run") is None
    orchestrator.run_nightly()
    assert orchestrator._system_state["last_nightly_run"] is not None


# ---------------------------------------------------------------------------
# Ack / state persistence
# ---------------------------------------------------------------------------

def test_run_once_acks_all_events(orchestrator):
    """Second run_once returns no duplicate signals."""
    orchestrator.bus.publish("trade:signal", STRATEGY, _make_signal())
    orchestrator.run_once()

    # Second poll should return no new events for the same consumer
    second_events = orchestrator.bus.poll(CONSUMER_ID, topics=["trade:signal"])
    assert len(second_events) == 0


def test_system_state_persisted_to_disk(orchestrator, tmp_path):
    orchestrator.bus.publish(
        "risk:global_status",
        "POLY_GLOBAL_RISK_GUARD",
        {"status": "ALERTE"},
    )
    orchestrator.run_once()

    store = PolyDataStore(base_path=str(tmp_path))
    state = store.read_json("orchestrator/system_state.json")
    assert state["global_risk_status"] == "ALERTE"


def test_lifecycle_persisted_to_disk(orchestrator, tmp_path):
    payload = {
        "action": "pause_strategy",
        "strategy": STRATEGY,
        "account_id": ACCOUNT_ID,
        "reason": "daily_drawdown_exceeded",
    }
    orchestrator.bus.publish("risk:kill_switch", "POLY_KILL_SWITCH", payload)
    orchestrator.run_once()

    store = PolyDataStore(base_path=str(tmp_path))
    lifecycle = store.read_json("orchestrator/strategy_lifecycle.json")
    assert lifecycle[STRATEGY]["lifecycle_phase"] == "paused"
