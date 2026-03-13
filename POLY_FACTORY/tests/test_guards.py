"""
POLY-T05 — Safeguard tests.

Four required scenarios (ticket POLY-T05):
  1. drawdown -6% → kill switch        (KILL_SWITCH)
  2. 6ème position → bloqué            (RISK_GUARDIAN)
  3. perte 4 000€ → arrêt total        (GLOBAL_RISK_GUARD)
  4. approval expiré → denied          (PROMOTION_GATE)
"""

import pytest
from datetime import datetime, timedelta, timezone

from core.poly_data_store import PolyDataStore
from core.poly_strategy_account import PolyStrategyAccount
from core.poly_strategy_registry import PolyStrategyRegistry
from risk.poly_kill_switch import (
    PolyKillSwitch,
    DAILY_DRAWDOWN_LIMIT_PCT,
    TOTAL_DRAWDOWN_LIMIT_PCT,
    MAX_CONSECUTIVE_LOSSES,
    WARNING_RATIO,
    LEVEL_OK,
    LEVEL_WARNING,
    LEVEL_PAUSE_DAILY,
    LEVEL_STOP_STRATEGY,
)
from risk.poly_risk_guardian import PolyRiskGuardian, MAX_POSITIONS
from risk.poly_global_risk_guard import (
    PolyGlobalRiskGuard,
    MAX_LOSS_EUR,
    ALERTE_THRESHOLD_EUR,
    CRITIQUE_THRESHOLD_EUR,
    STATUS_NORMAL,
    STATUS_ALERTE,
    STATUS_CRITIQUE,
    STATUS_ARRET_TOTAL,
)
from risk.poly_strategy_promotion_gate import (
    PolyStrategyPromotionGate,
    APPROVAL_EXPIRY_DAYS,
)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

STRATEGY = "POLY_GUARD_TEST"
ACCOUNT_ID = f"ACC_{STRATEGY}"
PLATFORM = "polymarket"
INITIAL_CAPITAL = 1000.0


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _now_str(offset_days: int = 0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=offset_days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Kill switch helpers
# ---------------------------------------------------------------------------

def _make_ks_account(
    base: str,
    daily_loss_eur: float = 0.0,
    extra_loss_eur: float = 0.0,
) -> PolyStrategyAccount:
    """Create account and optionally record losses for kill switch tests."""
    account = PolyStrategyAccount.create(STRATEGY, PLATFORM, base)
    if daily_loss_eur > 0:
        account.record_trade(-daily_loss_eur)
    if extra_loss_eur > 0:
        account.record_trade(-extra_loss_eur)
    return account


# ---------------------------------------------------------------------------
# Risk guardian helper
# ---------------------------------------------------------------------------

def _add_n_positions(
    guardian: PolyRiskGuardian,
    n: int,
    size_eur: float = 10.0,
    category: str = "arb",
) -> None:
    for i in range(n):
        guardian.add_position(STRATEGY, f"mkt-{i}", size_eur, category)


# ---------------------------------------------------------------------------
# Global risk guard helper
# ---------------------------------------------------------------------------

def _register_account_with_loss(
    guard: PolyGlobalRiskGuard,
    base: str,
    strategy: str,
    loss_eur: float,
) -> None:
    """Create account, record loss, register with guard."""
    account = PolyStrategyAccount.create(strategy, PLATFORM, base)
    account.record_trade(-loss_eur)
    guard.register(f"ACC_{strategy}")


# ---------------------------------------------------------------------------
# Promotion gate helper
# ---------------------------------------------------------------------------

def _setup_promotable_strategy(
    base: str,
    approval_age_days: int = 1,
    score: int = 75,
    include_approval: bool = True,
    approval_fields: dict | None = None,
    global_risk_status: str = "NORMAL",
) -> None:
    """Write all state files so all 10 promotion checks pass.

    approval_age_days controls check 6 (expiry).
    score controls check 3.
    include_approval controls check 5.
    approval_fields overrides the approval payload (for missing-fields tests).
    global_risk_status controls check 8.
    """
    store = PolyDataStore(base_path=base)

    # Check 1: registry — register + set status awaiting_promotion
    reg = PolyStrategyRegistry(base_path=base)
    reg.register(STRATEGY, "arbitrage", PLATFORM, {"param": 1})
    reg.update_status(STRATEGY, "awaiting_promotion")

    # Check 2: account — 50 trades, 20 paper days
    account_id = f"ACC_{STRATEGY}"
    paper_started = _now_str(-20)
    account_data = {
        "account_id": account_id,
        "strategy": STRATEGY,
        "status": "paper_testing",
        "platform": PLATFORM,
        "capital": {
            "initial": INITIAL_CAPITAL,
            "current": INITIAL_CAPITAL,
            "available": INITIAL_CAPITAL,
        },
        "pnl": {"total": 0.0, "daily": 0.0, "session": 0.0},
        "drawdown": {
            "high_water_mark": INITIAL_CAPITAL,
            "current_drawdown_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "daily_pnl_pct": 0.0,
        },
        "performance": {
            "total_trades": 50,
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
    store.write_json(f"accounts/{account_id}.json", account_data)

    # Check 3: eval score
    store.write_json("evaluation/strategy_scores.json", {
        STRATEGY: {"score": score}
    })

    # Check 4: decay — healthy
    store.write_json("evaluation/decay_alerts.json", {
        STRATEGY: {"severity": "HEALTHY"}
    })

    # Checks 5-7: human approval
    if include_approval:
        fields = approval_fields if approval_fields is not None else {
            "approved_at": _now_str(-approval_age_days),
            "capital_max": 1000,
            "max_per_trade": 50,
            "kill_switch": True,
        }
        store.write_json("human/approvals.json", {STRATEGY: fields})

    # Checks 8-9: global risk state
    store.write_json("risk/global_risk_state.json", {
        "status": global_risk_status,
        "total_loss_eur": 0.0,
    })

    # Check 10: wallet balance
    store.write_json("feeds/wallet_raw_positions.json", {
        "USDC.e": 1500.0,
    })


# ===========================================================================
# Class 1: TestKillSwitchDrawdown — ticket requirement 1
# ===========================================================================

class TestKillSwitchDrawdown:
    """Daily drawdown -6% and other kill switch scenarios."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.base = str(tmp_path)
        self.ks = PolyKillSwitch(base_path=self.base)

    def test_daily_drawdown_triggers_pause_daily(self):
        # 6% daily loss (threshold = -5%)
        _make_ks_account(self.base, daily_loss_eur=60.0)
        result = self.ks.evaluate(STRATEGY, ACCOUNT_ID)
        assert result["level"] == LEVEL_PAUSE_DAILY

    def test_daily_drawdown_reason(self):
        _make_ks_account(self.base, daily_loss_eur=60.0)
        result = self.ks.evaluate(STRATEGY, ACCOUNT_ID)
        assert result["reason"] == "daily_drawdown_exceeded"

    def test_daily_drawdown_blocks_pre_trade(self):
        _make_ks_account(self.base, daily_loss_eur=60.0)
        self.ks.evaluate(STRATEGY, ACCOUNT_ID)  # populate _status
        pre = self.ks.check_pre_trade(STRATEGY)
        assert pre["allowed"] is False

    def test_total_drawdown_triggers_stop_strategy(self):
        # -31% total drawdown (threshold = -30%)
        # record_trade(-310): current=690, HWM=1000, dd=-31%
        _make_ks_account(self.base, daily_loss_eur=310.0)
        result = self.ks.evaluate(STRATEGY, ACCOUNT_ID)
        assert result["level"] == LEVEL_STOP_STRATEGY

    def test_total_drawdown_reason(self):
        _make_ks_account(self.base, daily_loss_eur=310.0)
        result = self.ks.evaluate(STRATEGY, ACCOUNT_ID)
        assert result["reason"] == "total_drawdown_exceeded"

    def test_consecutive_losses_triggers_pause(self):
        # Create account (no losses), set 3 consecutive losses via record_trade_result
        _make_ks_account(self.base)
        for _ in range(MAX_CONSECUTIVE_LOSSES):
            self.ks.record_trade_result(STRATEGY, -1.0)
        result = self.ks.evaluate(STRATEGY, ACCOUNT_ID)
        assert result["level"] == LEVEL_PAUSE_DAILY
        assert result["reason"] == "consecutive_losses_exceeded"

    def test_below_threshold_level_ok(self):
        # -3% daily loss: below warning threshold (-4%), should be OK
        _make_ks_account(self.base, daily_loss_eur=30.0)
        result = self.ks.evaluate(STRATEGY, ACCOUNT_ID)
        assert result["level"] == LEVEL_OK
        pre = self.ks.check_pre_trade(STRATEGY)
        assert pre["allowed"] is True

    def test_approaching_limit_warning(self):
        # -4.2% daily loss: below pause threshold (-5%) but below warning (-4%)
        _make_ks_account(self.base, daily_loss_eur=42.0)
        result = self.ks.evaluate(STRATEGY, ACCOUNT_ID)
        assert result["level"] == LEVEL_WARNING
        pre = self.ks.check_pre_trade(STRATEGY)
        assert pre["allowed"] is True


# ===========================================================================
# Class 2: TestRiskGuardianPositionLimit — ticket requirement 2
# ===========================================================================

class TestRiskGuardianPositionLimit:
    """6th position blocked by risk guardian (MAX_POSITIONS = 5)."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.guardian = PolyRiskGuardian(base_path=str(tmp_path))

    def test_fifth_position_allowed(self):
        _add_n_positions(self.guardian, 4)
        result = self.guardian.check(10.0, "arb", 1000.0)
        assert result["allowed"] is True

    def test_sixth_position_blocked(self):
        _add_n_positions(self.guardian, MAX_POSITIONS)  # 5 positions
        result = self.guardian.check(10.0, "arb", 1000.0)
        assert result["allowed"] is False

    def test_sixth_position_blocked_by(self):
        _add_n_positions(self.guardian, MAX_POSITIONS)
        result = self.guardian.check(10.0, "arb", 1000.0)
        assert result["blocked_by"] == "max_positions"

    def test_positions_ok_after_close(self):
        _add_n_positions(self.guardian, MAX_POSITIONS)
        self.guardian.close_position(STRATEGY, "mkt-0")
        result = self.guardian.check(10.0, "arb", 1000.0)
        assert result["allowed"] is True

    def test_exposure_limit_blocked(self):
        # 850€ existing exposure out of 1000€ total = 85% > 80%
        self.guardian.add_position(STRATEGY, "mkt-big", 850.0, "arb")
        result = self.guardian.check(10.0, "arb", 1000.0)
        assert result["allowed"] is False
        assert result["blocked_by"] == "max_exposure"


# ===========================================================================
# Class 3: TestGlobalRiskGuardHalt — ticket requirement 3
# ===========================================================================

class TestGlobalRiskGuardHalt:
    """4 000€ cumulative loss triggers ARRET_TOTAL and halts all trading."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.base = str(tmp_path)
        self.guard = PolyGlobalRiskGuard(base_path=self.base)

    def _register_loss(self, strategy: str, loss_eur: float) -> None:
        _register_account_with_loss(self.guard, self.base, strategy, loss_eur)

    def test_4000_eur_loss_triggers_arret_total(self):
        for i in range(4):
            self._register_loss(f"POLY_STRAT_{i}", 1000.0)
        result = self.guard.evaluate()
        assert result["status"] == STATUS_ARRET_TOTAL

    def test_arret_total_action_is_halt(self):
        for i in range(4):
            self._register_loss(f"POLY_STRAT_{i}", 1000.0)
        result = self.guard.evaluate()
        assert result["action_taken"] == "halt_all_trading"

    def test_arret_total_blocks_pre_trade(self):
        for i in range(4):
            self._register_loss(f"POLY_STRAT_{i}", 1000.0)
        self.guard.evaluate()  # update persisted state
        pre = self.guard.check_pre_trade()
        assert pre["allowed"] is False

    def test_3999_eur_critique_not_halted(self):
        # 3999€ → CRITIQUE but trading still allowed
        self._register_loss("POLY_STRAT_A", 1000.0)
        self._register_loss("POLY_STRAT_B", 1000.0)
        self._register_loss("POLY_STRAT_C", 1000.0)
        self._register_loss("POLY_STRAT_D", 999.0)
        result = self.guard.evaluate()
        assert result["status"] == STATUS_CRITIQUE
        pre = self.guard.check_pre_trade()
        assert pre["allowed"] is True

    def test_2000_eur_triggers_alerte(self):
        self._register_loss("POLY_STRAT_A", 1000.0)
        self._register_loss("POLY_STRAT_B", 1000.0)
        result = self.guard.evaluate()
        assert result["status"] == STATUS_ALERTE

    def test_below_threshold_normal(self):
        self._register_loss("POLY_STRAT_A", 500.0)
        result = self.guard.evaluate()
        assert result["status"] == STATUS_NORMAL

    def test_pct_used_at_max_loss(self):
        for i in range(4):
            self._register_loss(f"POLY_STRAT_{i}", 1000.0)
        result = self.guard.evaluate()
        assert result["pct_used"] == 1.0


# ===========================================================================
# Class 4: TestPromotionGateExpiredApproval — ticket requirement 4
# ===========================================================================

class TestPromotionGateExpiredApproval:
    """Expired human approval causes promotion denial at check 6."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.base = str(tmp_path)
        # Gate is created AFTER _setup_promotable_strategy in each test so the
        # registry is loaded from disk with the correct data already present.

    def _gate(self) -> PolyStrategyPromotionGate:
        return PolyStrategyPromotionGate(base_path=self.base)

    def test_expired_approval_denied(self):
        _setup_promotable_strategy(self.base, approval_age_days=APPROVAL_EXPIRY_DAYS + 1)
        result = self._gate().evaluate(STRATEGY)
        assert result["approved"] is False
        assert result["check_failed"] == "approval_expiry"

    def test_expired_approval_reason(self):
        _setup_promotable_strategy(self.base, approval_age_days=APPROVAL_EXPIRY_DAYS + 1)
        result = self._gate().evaluate(STRATEGY)
        assert result["reason"] == "approval_expired"

    def test_valid_approval_all_10_checks_pass(self):
        _setup_promotable_strategy(self.base, approval_age_days=1)
        result = self._gate().evaluate(STRATEGY)
        assert result["approved"] is True

    def test_missing_approval_denied_at_check5(self):
        _setup_promotable_strategy(self.base, include_approval=False)
        result = self._gate().evaluate(STRATEGY)
        assert result["approved"] is False
        assert result["check_failed"] == "approval_exists"

    def test_approval_missing_required_field(self):
        # Approval present but missing "kill_switch"
        _setup_promotable_strategy(
            self.base,
            approval_age_days=1,
            approval_fields={
                "approved_at": _now_str(-1),
                "capital_max": 1000,
                "max_per_trade": 50,
                # "kill_switch" intentionally omitted
            },
        )
        result = self._gate().evaluate(STRATEGY)
        assert result["approved"] is False
        assert result["check_failed"] == "approval_limits"

    def test_global_risk_not_normal_denied(self):
        _setup_promotable_strategy(
            self.base,
            approval_age_days=1,
            global_risk_status="CRITIQUE",
        )
        result = self._gate().evaluate(STRATEGY)
        assert result["approved"] is False
        assert result["check_failed"] == "global_risk_status"

    def test_eval_score_too_low_denied(self):
        _setup_promotable_strategy(self.base, score=50)
        result = self._gate().evaluate(STRATEGY)
        assert result["approved"] is False
        assert result["check_failed"] == "eval_score"
