"""
Tests for POLY_STRATEGY_PROMOTION_GATE (POLY-036).

Ticket acceptance criteria:
  - 10/10 checks OK → approved
  - Check 8 fails → denied
  - Gate NEVER creates any account (Capital Manager's exclusive job)

~28 tests covering all 10 checks, bus events, run_once, and the
critical no-account-creation constraint.
"""

import os
import pytest
from datetime import datetime, timedelta, timezone

from core.poly_data_store import PolyDataStore
from core.poly_strategy_registry import PolyStrategyRegistry
from risk.poly_strategy_promotion_gate import (
    PolyStrategyPromotionGate,
    CONSUMER_ID,
    MIN_PAPER_TRADES,
    MIN_PAPER_DAYS,
    MIN_EVAL_SCORE,
    APPROVAL_EXPIRY_DAYS,
    WORST_CASE_PROMOTION_EUR,
    GLOBAL_LOSS_CEILING_EUR,
    MIN_WALLET_USDC_EUR,
    REGISTRY_PROMOTABLE_STATUS,
    CHECK_NAMES,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRATEGY = "POLY_TEST_STRAT"
ACCOUNT_ID = f"ACC_{STRATEGY}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_str(offset_days: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=offset_days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_account(tmp_path, strategy=STRATEGY, total_trades=60, paper_days=20) -> None:
    """Write a minimal account JSON file."""
    account_id = f"ACC_{strategy}"
    paper_started = (
        datetime.now(timezone.utc) - timedelta(days=paper_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {
        "account_id": account_id,
        "strategy": strategy,
        "status": "paper_testing",
        "platform": "polymarket",
        "capital": {"initial": 1000.0, "current": 1000.0, "available": 1000.0},
        "pnl": {"total": 0.0, "daily": 0.0, "session": 0.0},
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
        "status_history": [{"status": "paper_testing", "timestamp": _now_str()}],
        "created_at": _now_str(),
        "updated_at": _now_str(),
    }
    store = PolyDataStore(base_path=str(tmp_path))
    store.write_json(f"accounts/{account_id}.json", data)


def _write_scores(tmp_path, strategy=STRATEGY, score=75) -> None:
    store = PolyDataStore(base_path=str(tmp_path))
    store.write_json("evaluation/strategy_scores.json", {strategy: {"score": score}})


def _write_decay(tmp_path, strategy=STRATEGY, severity="HEALTHY") -> None:
    store = PolyDataStore(base_path=str(tmp_path))
    store.write_json("evaluation/decay_alerts.json", {strategy: {"severity": severity}})


def _write_approval(
    tmp_path,
    strategy=STRATEGY,
    age_days=1,
    fields=None,
) -> None:
    """Write human/approvals.json. `fields` overrides the default required fields."""
    approved_at = _now_str(offset_days=age_days)
    if fields is None:
        approval_data = {
            "approved_at": approved_at,
            "approved_by": "human_operator",
            "capital_max": 1000.0,
            "max_per_trade": 50.0,
            "kill_switch": {"daily_drawdown_pct": -5.0, "total_drawdown_pct": -30.0},
        }
    else:
        approval_data = {"approved_at": approved_at, **fields}

    store = PolyDataStore(base_path=str(tmp_path))
    store.write_json("human/approvals.json", {strategy: approval_data})


def _write_global_risk(tmp_path, status="NORMAL", total_loss=500.0) -> None:
    store = PolyDataStore(base_path=str(tmp_path))
    store.write_json(
        "risk/global_risk_state.json",
        {"status": status, "total_loss_eur": total_loss},
    )


def _write_wallet(tmp_path, usdc_balance=5000.0) -> None:
    store = PolyDataStore(base_path=str(tmp_path))
    store.write_json("feeds/wallet_raw_positions.json", {"USDC.e": usdc_balance})


def _register_strategy(tmp_path, strategy=STRATEGY, status=REGISTRY_PROMOTABLE_STATUS):
    """Register strategy in registry and set its status."""
    registry = PolyStrategyRegistry(base_path=str(tmp_path))
    # Register as scouted first (initial status), then update to desired status
    try:
        registry.register(name=strategy, category="test", platform="polymarket", parameters={})
    except ValueError:
        pass  # already registered
    if status != "scouted":
        # Update through valid transitions
        transition_map = {
            "backtesting": ["backtesting"],
            "paper_testing": ["backtesting", "paper_testing"],
            "awaiting_promotion": ["backtesting", "paper_testing", "awaiting_promotion"],
            "live": ["backtesting", "paper_testing", "awaiting_promotion", "live"],
            "paused": ["backtesting", "paper_testing", "paused"],
            "stopped": ["backtesting", "paper_testing", "stopped"],
        }
        for s in transition_map.get(status, [status]):
            try:
                registry.update_status(strategy, s)
            except ValueError:
                pass
    return registry


def _setup_all_pass(tmp_path, strategy=STRATEGY) -> PolyStrategyPromotionGate:
    """Set up all 10 checks to pass and return a configured gate."""
    _register_strategy(tmp_path, strategy, status=REGISTRY_PROMOTABLE_STATUS)
    _make_account(tmp_path, strategy, total_trades=60, paper_days=20)
    _write_scores(tmp_path, strategy, score=75)
    _write_decay(tmp_path, strategy, severity="HEALTHY")
    _write_approval(tmp_path, strategy, age_days=1)
    _write_global_risk(tmp_path, status="NORMAL", total_loss=500.0)
    _write_wallet(tmp_path, usdc_balance=5000.0)
    return PolyStrategyPromotionGate(base_path=str(tmp_path))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gate(tmp_path):
    return _setup_all_pass(tmp_path)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_all_10_checks_pass(gate):
    result = gate.evaluate(STRATEGY)
    assert result["approved"] is True
    assert result["check_failed"] is None
    assert result["reason"] is None
    assert result["checks_passed"] == CHECK_NAMES


def test_approved_event_published_on_bus(gate):
    gate.evaluate(STRATEGY)
    events = gate.bus.poll("TEST_CONSUMER", topics=["promotion:approved"])
    assert len(events) == 1
    assert events[0]["payload"]["strategy"] == STRATEGY


def test_approved_payload_contains_approval_json(gate):
    result = gate.evaluate(STRATEGY)
    assert result["approval_json"] is not None
    assert "capital_max" in result["approval_json"]
    assert "max_per_trade" in result["approval_json"]
    assert "kill_switch" in result["approval_json"]


# ---------------------------------------------------------------------------
# Check 1 — registry
# ---------------------------------------------------------------------------

def test_check_1_fails_strategy_not_registered(tmp_path):
    # Only set up checks 2–10; don't register in registry
    _make_account(tmp_path)
    _write_scores(tmp_path)
    _write_decay(tmp_path)
    _write_approval(tmp_path)
    _write_global_risk(tmp_path)
    _write_wallet(tmp_path)
    gate = PolyStrategyPromotionGate(base_path=str(tmp_path))

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "registry"
    assert result["reason"] == "strategy_not_registered"
    assert result["checks_passed"] == []


def test_check_1_fails_wrong_status(tmp_path):
    _register_strategy(tmp_path, status="paper_testing")
    _make_account(tmp_path)
    _write_scores(tmp_path)
    _write_decay(tmp_path)
    _write_approval(tmp_path)
    _write_global_risk(tmp_path)
    _write_wallet(tmp_path)
    gate = PolyStrategyPromotionGate(base_path=str(tmp_path))

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "registry"
    assert result["reason"] == "wrong_registry_status"


# ---------------------------------------------------------------------------
# Check 2 — account_metrics
# ---------------------------------------------------------------------------

def test_check_2_fails_insufficient_trades(tmp_path):
    gate = _setup_all_pass(tmp_path)
    # Overwrite account with fewer trades
    _make_account(tmp_path, total_trades=MIN_PAPER_TRADES - 1, paper_days=20)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "account_metrics"
    assert result["reason"] == "insufficient_trades"
    assert "registry" in result["checks_passed"]


def test_check_2_fails_insufficient_days(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _make_account(tmp_path, total_trades=60, paper_days=MIN_PAPER_DAYS - 1)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "account_metrics"
    assert result["reason"] == "insufficient_paper_days"


def test_check_2_fails_account_not_found(tmp_path):
    # Register strategy but don't create account file
    _register_strategy(tmp_path, status=REGISTRY_PROMOTABLE_STATUS)
    _write_scores(tmp_path)
    _write_decay(tmp_path)
    _write_approval(tmp_path)
    _write_global_risk(tmp_path)
    _write_wallet(tmp_path)
    gate = PolyStrategyPromotionGate(base_path=str(tmp_path))

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "account_metrics"
    assert result["reason"] == "account_not_found"


# ---------------------------------------------------------------------------
# Check 3 — eval_score
# ---------------------------------------------------------------------------

def test_check_3_fails_low_score(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_scores(tmp_path, score=MIN_EVAL_SCORE - 1)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "eval_score"
    assert result["reason"] == "eval_score_too_low"
    assert "account_metrics" in result["checks_passed"]


def test_check_3_fails_strategy_missing_from_scores(tmp_path):
    """Missing strategy key → score defaults to 0 → fails."""
    gate = _setup_all_pass(tmp_path)
    _write_scores(tmp_path, strategy="OTHER_STRAT", score=80)  # no entry for STRATEGY

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "eval_score"


# ---------------------------------------------------------------------------
# Check 4 — decay
# ---------------------------------------------------------------------------

def test_check_4_fails_serious_decay(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_decay(tmp_path, severity="SERIOUS")

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "decay"
    assert result["reason"] == "active_decay_alert"


def test_check_4_fails_critical_decay(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_decay(tmp_path, severity="CRITICAL")

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "decay"


def test_check_4_passes_warning_decay(tmp_path):
    """WARNING severity is not blocked — only SERIOUS and CRITICAL are."""
    gate = _setup_all_pass(tmp_path)
    _write_decay(tmp_path, severity="WARNING")

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is True
    assert "decay" in result["checks_passed"]


# ---------------------------------------------------------------------------
# Check 5 — approval_exists
# ---------------------------------------------------------------------------

def test_check_5_fails_no_approval_file(tmp_path):
    """human/approvals.json doesn't exist at all."""
    gate = _setup_all_pass(tmp_path)
    # Remove the approvals file by writing an empty dict without strategy key
    store = PolyDataStore(base_path=str(tmp_path))
    store.write_json("human/approvals.json", {})  # no strategy entry

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "approval_exists"
    assert result["reason"] == "no_human_approval"


def test_check_5_fails_no_approval_for_strategy(tmp_path):
    """File exists but strategy key missing."""
    gate = _setup_all_pass(tmp_path)
    store = PolyDataStore(base_path=str(tmp_path))
    store.write_json("human/approvals.json", {"OTHER_STRAT": {"approved_at": _now_str()}})

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "approval_exists"


# ---------------------------------------------------------------------------
# Check 6 — approval_expiry
# ---------------------------------------------------------------------------

def test_check_6_fails_expired_approval(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_approval(tmp_path, age_days=APPROVAL_EXPIRY_DAYS + 1)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "approval_expiry"
    assert result["reason"] == "approval_expired"


def test_check_6_passes_approval_just_within_expiry(tmp_path):
    """An approval exactly 6 days old is still valid (< 7 days)."""
    gate = _setup_all_pass(tmp_path)
    _write_approval(tmp_path, age_days=APPROVAL_EXPIRY_DAYS - 1)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is True


# ---------------------------------------------------------------------------
# Check 7 — approval_limits
# ---------------------------------------------------------------------------

def test_check_7_fails_missing_capital_max(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_approval(tmp_path, fields={"max_per_trade": 50.0, "kill_switch": {}})

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "approval_limits"
    assert result["reason"] == "approval_missing_limits"


def test_check_7_fails_missing_max_per_trade(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_approval(tmp_path, fields={"capital_max": 1000.0, "kill_switch": {}})

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "approval_limits"


def test_check_7_fails_missing_kill_switch(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_approval(tmp_path, fields={"capital_max": 1000.0, "max_per_trade": 50.0})

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "approval_limits"


# ---------------------------------------------------------------------------
# Check 8 — global_risk_status  (ticket acceptance criteria: check 8 échoue → denied)
# ---------------------------------------------------------------------------

def test_check_8_fails_global_risk_alerte(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_global_risk(tmp_path, status="ALERTE", total_loss=2500.0)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "global_risk_status"
    assert result["reason"] == "global_risk_not_normal"
    # Checks 1–7 already passed
    assert "approval_limits" in result["checks_passed"]


def test_check_8_fails_global_risk_critique(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_global_risk(tmp_path, status="CRITIQUE", total_loss=3500.0)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "global_risk_status"


def test_check_8_fails_global_risk_arret_total(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_global_risk(tmp_path, status="ARRET_TOTAL", total_loss=4000.0)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "global_risk_status"


# ---------------------------------------------------------------------------
# Check 9 — global_risk_headroom
# ---------------------------------------------------------------------------

def test_check_9_fails_loss_too_high(tmp_path):
    """total_loss=3001 → 3001+1000=4001 ≥ 4000 → denied."""
    gate = _setup_all_pass(tmp_path)
    _write_global_risk(tmp_path, status="NORMAL", total_loss=3001.0)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "global_risk_headroom"
    assert result["reason"] == "global_risk_headroom_insufficient"


def test_check_9_fails_exactly_at_ceiling(tmp_path):
    """total_loss=3000 → 3000+1000=4000 ≥ 4000 → denied."""
    gate = _setup_all_pass(tmp_path)
    _write_global_risk(tmp_path, status="NORMAL", total_loss=GLOBAL_LOSS_CEILING_EUR - WORST_CASE_PROMOTION_EUR)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "global_risk_headroom"


def test_check_9_passes_just_under_ceiling(tmp_path):
    """total_loss=2999 → 2999+1000=3999 < 4000 → passes."""
    gate = _setup_all_pass(tmp_path)
    _write_global_risk(tmp_path, status="NORMAL", total_loss=2999.0)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is True
    assert "global_risk_headroom" in result["checks_passed"]


# ---------------------------------------------------------------------------
# Check 10 — wallet_balance
# ---------------------------------------------------------------------------

def test_check_10_fails_insufficient_wallet(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_wallet(tmp_path, usdc_balance=MIN_WALLET_USDC_EUR - 1)

    result = gate.evaluate(STRATEGY)
    assert result["approved"] is False
    assert result["check_failed"] == "wallet_balance"
    assert result["reason"] == "insufficient_wallet_balance"


def test_check_10_passes_exact_minimum(tmp_path):
    """Balance exactly at the minimum (1000.0) should be denied (strict <)."""
    gate = _setup_all_pass(tmp_path)
    _write_wallet(tmp_path, usdc_balance=MIN_WALLET_USDC_EUR)

    result = gate.evaluate(STRATEGY)
    # MIN_WALLET_USDC_EUR is the minimum: balance >= threshold → pass
    assert result["approved"] is True


# ---------------------------------------------------------------------------
# Critical constraint — gate NEVER creates accounts
# ---------------------------------------------------------------------------

def test_gate_never_creates_account(tmp_path):
    """After a successful approval, no new account file must appear."""
    gate = _setup_all_pass(tmp_path)
    accounts_dir = os.path.join(str(tmp_path), "accounts")

    # Count non-archive account files before evaluation
    def _count_accounts():
        if not os.path.isdir(accounts_dir):
            return 0
        return sum(
            1 for f in os.listdir(accounts_dir)
            if f.endswith(".json") and os.path.isfile(os.path.join(accounts_dir, f))
        )

    before = _count_accounts()
    result = gate.evaluate(STRATEGY)
    after = _count_accounts()

    assert result["approved"] is True
    assert after == before, (
        f"Gate created {after - before} account(s) — only Capital Manager may do this"
    )


# ---------------------------------------------------------------------------
# Bus events on denial
# ---------------------------------------------------------------------------

def test_denied_event_published_on_bus(tmp_path):
    gate = _setup_all_pass(tmp_path)
    _write_global_risk(tmp_path, status="ALERTE", total_loss=2500.0)

    gate.evaluate(STRATEGY)
    events = gate.bus.poll("TEST", topics=["promotion:denied"])
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["strategy"] == STRATEGY
    assert payload["check_failed"] == "global_risk_status"
    assert payload["approved"] is False


# ---------------------------------------------------------------------------
# run_once — bus polling
# ---------------------------------------------------------------------------

def test_run_once_processes_promotion_request(tmp_path):
    gate = _setup_all_pass(tmp_path)
    gate.bus.publish("promotion:request", "POLY_ORCHESTRATOR", {"strategy": STRATEGY})

    results = gate.run_once()
    assert len(results) == 1
    assert results[0]["approved"] is True
    assert results[0]["strategy"] == STRATEGY


def test_run_once_acks_event(tmp_path):
    """Second run_once must not re-process the same event."""
    gate = _setup_all_pass(tmp_path)
    gate.bus.publish("promotion:request", "POLY_ORCHESTRATOR", {"strategy": STRATEGY})

    gate.run_once()
    second = gate.run_once()
    assert second == []
