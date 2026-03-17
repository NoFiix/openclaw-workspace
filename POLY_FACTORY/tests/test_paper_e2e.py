"""
POLY-T04 — End-to-end paper trading pipeline tests.

Tests the full signal → 7-filter chain → paper execution → account update pipeline.

Three required scenarios (ticket POLY-T04):
  1. arb → filters → trade → account MAJ  (happy path)
  2. marché illiquide → rejeté filtre 1   (executability < 40)
  3. marché ambigu → rejeté filtre 2      (ambiguity ≥ 3)
"""

import pytest
from datetime import datetime, timezone

from core.poly_data_store import PolyDataStore
from core.poly_factory_orchestrator import (
    PolyFactoryOrchestrator,
    FILTER_NAMES,
    MAX_AMBIGUITY_SCORE,
)
from core.poly_strategy_account import PolyStrategyAccount
from execution.poly_paper_execution_engine import (
    PolyPaperExecutionEngine,
    FEE_RATE,
    PAPER_TRADES_LOG,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRATEGY = "POLY_ARB_SCANNER"
ACCOUNT_ID = f"ACC_{STRATEGY}"
MARKET_ID = "market-e2e-001"
PLATFORM = "polymarket"


# ---------------------------------------------------------------------------
# Mock stubs
# ---------------------------------------------------------------------------

class MockKillSwitch:
    def __init__(self, allowed=True):
        self._allowed = allowed

    def check_pre_trade(self, strategy):
        return {
            "allowed": self._allowed,
            "level": "OK" if self._allowed else "PAUSE_DAILY",
            "reason": None if self._allowed else "kill_switch_blocked",
        }

    def reset_daily(self, strategy):
        pass


class MockRiskGuardian:
    def check(self, proposed_size_eur, proposed_category, total_capital_eur):
        return {"allowed": True, "blocked_by": None, "checks": {}}


class MockCapitalManager:
    def check_capital(self, account_id, size_eur):
        return {
            "allowed": True,
            "available_capital_eur": 1000.0,
            "required_eur": size_eur,
            "reason": None,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _setup_state(
    base: str,
    executability_score: int = 75,
    slippage_1k: float = 0.005,
    depth_usd: float = 10_000.0,
    spread_bps: float = 0.0,
) -> None:
    """Create account and write market_structure.json to disk."""
    store = PolyDataStore(base_path=base)

    account_data = {
        "account_id": ACCOUNT_ID,
        "strategy": STRATEGY,
        "status": "paper_testing",
        "platform": PLATFORM,
        "capital": {"initial": 1000.0, "current": 1000.0, "available": 1000.0},
        "pnl": {"total": 0.0, "daily": 0.0, "session": 0.0},
        "drawdown": {
            "high_water_mark": 1000.0,
            "current_drawdown_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "daily_pnl_pct": 0.0,
        },
        "performance": {
            "total_trades": 0,
            "paper_started": _now_str(),
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
    store.write_json(f"accounts/{ACCOUNT_ID}.json", account_data)

    structure = {
        MARKET_ID: {
            "executability_score": executability_score,
            "slippage_1k": slippage_1k,
            "depth_usd": depth_usd,
            "spread_bps": spread_bps,
        }
    }
    store.write_json("feeds/market_structure.json", structure)


def _make_orch(base: str, kill_switch=None) -> PolyFactoryOrchestrator:
    """Create orchestrator with mocks; seed price_cache and resolution_cache."""
    ks = kill_switch or MockKillSwitch(allowed=True)
    orch = PolyFactoryOrchestrator(
        base_path=base,
        kill_switch=ks,
        risk_guardian=MockRiskGuardian(),
        capital_manager=MockCapitalManager(),
    )
    orch._price_cache[MARKET_ID] = {
        "market_id": MARKET_ID,
        "data_status": "VALID",
        "yes_ask": 0.55,
        "no_ask": 0.45,
    }
    orch._resolution_cache[MARKET_ID] = {
        "market_id": MARKET_ID,
        "ambiguity_score": 1,
    }
    return orch


def _happy_signal(
    market_id: str = MARKET_ID,
    signal_type: str = "arb",
) -> dict:
    """Minimal valid trade:signal payload."""
    return {
        "market_id": market_id,
        "strategy": STRATEGY,
        "account_id": ACCOUNT_ID,
        "platform": PLATFORM,
        "direction": "BUY_YES",
        "signal_type": signal_type,
        "confidence": 0.70,
        "suggested_size_eur": 50.0,
    }


def _execute_from_filter(
    engine: PolyPaperExecutionEngine,
    filter_result: dict,
    signal: dict,
) -> dict:
    """Bridge filter chain result → paper engine execute payload."""
    payload = {
        "strategy": signal["strategy"],
        "account_id": signal["account_id"],
        "market_id": signal["market_id"],
        "platform": signal["platform"],
        "direction": signal["direction"],
        "size_eur": filter_result["validated_size_eur"],
        "expected_fill_price": filter_result["price"],
        "slippage_estimated": filter_result.get("slippage_estimated") or 0.005,
    }
    return engine.execute(payload)


# ===========================================================================
# Class 1: TestArbE2E — happy path (ticket requirement 1)
# ===========================================================================

class TestArbE2E:
    """Happy path: arb signal passes all 7 filters, trade executed, account updated."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.base = str(tmp_path)
        _setup_state(self.base)
        self.orch = _make_orch(self.base)
        self.engine = PolyPaperExecutionEngine(base_path=self.base)
        self.signal = _happy_signal()
        self.filter_result = self.orch._run_filter_chain(self.signal)

    def test_all_7_filters_pass(self):
        assert self.filter_result["passed"] is True
        assert self.filter_result["filters_passed"] == FILTER_NAMES

    def test_trade_executed_and_account_debited(self):
        capital_before = PolyStrategyAccount.load(ACCOUNT_ID, self.base).data["capital"]["current"]

        _execute_from_filter(self.engine, self.filter_result, self.signal)

        capital_after = PolyStrategyAccount.load(ACCOUNT_ID, self.base).data["capital"]["current"]
        assert capital_after < capital_before

    def test_account_trade_count_incremented(self):
        assert PolyStrategyAccount.load(ACCOUNT_ID, self.base).data["performance"]["total_trades"] == 0

        _execute_from_filter(self.engine, self.filter_result, self.signal)

        assert PolyStrategyAccount.load(ACCOUNT_ID, self.base).data["performance"]["total_trades"] == 1

    def test_trade_logged_to_jsonl(self):
        _execute_from_filter(self.engine, self.filter_result, self.signal)

        store = PolyDataStore(base_path=self.base)
        records = store.read_jsonl(PAPER_TRADES_LOG)
        assert len(records) == 1
        assert records[0]["market_id"] == MARKET_ID

    def test_bus_event_paper_executed(self):
        _execute_from_filter(self.engine, self.filter_result, self.signal)

        store = PolyDataStore(base_path=self.base)
        events = store.read_jsonl("bus/pending_events.jsonl")
        topics = [e["topic"] for e in events]
        assert "trade:paper_executed" in topics

    def test_trade_id_format(self):
        result = _execute_from_filter(self.engine, self.filter_result, self.signal)
        assert result["trade_id"].startswith("TRD_")

    def test_fees_deducted(self):
        result = _execute_from_filter(self.engine, self.filter_result, self.signal)
        expected_fees = result["size_eur"] * FEE_RATE
        assert abs(result["fees"] - expected_fees) < 1e-9


# ===========================================================================
# Class 2: TestIlliquidMarketFilter1 — ticket requirement 2
# ===========================================================================

class TestIlliquidMarketFilter1:
    """Illiquid market rejected at filter 1 (microstructure)."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.base = str(tmp_path)

    def _orch_with_structure(
        self,
        executability_score: int = 75,
        slippage_1k: float = 0.005,
        depth_usd: float = 10_000.0,
    ) -> PolyFactoryOrchestrator:
        _setup_state(
            self.base,
            executability_score=executability_score,
            slippage_1k=slippage_1k,
            depth_usd=depth_usd,
        )
        return _make_orch(self.base)

    def test_low_executability_rejected_at_filter1(self):
        orch = self._orch_with_structure(executability_score=20)
        result = orch._run_filter_chain(_happy_signal())
        assert result["passed"] is False
        assert result["rejected_by"] == "microstructure"

    def test_low_executability_reason(self):
        orch = self._orch_with_structure(executability_score=20)
        result = orch._run_filter_chain(_happy_signal())
        assert result["reason"] == "low_executability_score"

    def test_high_slippage_rejected_at_filter1(self):
        # depth=500 → slippage = 30/500 = 0.06 > 0.03
        orch = self._orch_with_structure(depth_usd=500.0)
        result = orch._run_filter_chain(_happy_signal())
        assert result["passed"] is False
        assert result["rejected_by"] == "microstructure"

    def test_high_slippage_reason(self):
        orch = self._orch_with_structure(depth_usd=500.0)
        result = orch._run_filter_chain(_happy_signal())
        assert result["reason"] == "high_slippage"

    def test_no_structure_data_rejected(self):
        _setup_state(self.base)
        orch = _make_orch(self.base)
        # Remove from both cache and disk
        orch._market_structure_cache.pop(MARKET_ID, None)
        PolyDataStore(base_path=self.base).write_json("feeds/market_structure.json", {})

        result = orch._run_filter_chain(_happy_signal())
        assert result["passed"] is False
        assert result["rejected_by"] == "microstructure"


# ===========================================================================
# Class 3: TestAmbiguousMarketFilter2 — ticket requirement 3
# ===========================================================================

class TestAmbiguousMarketFilter2:
    """Ambiguous market rejected at filter 2 (resolution)."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.base = str(tmp_path)
        _setup_state(self.base)

    def test_high_ambiguity_rejected_at_filter2(self):
        orch = _make_orch(self.base)
        orch._resolution_cache[MARKET_ID] = {
            "market_id": MARKET_ID,
            "ambiguity_score": MAX_AMBIGUITY_SCORE,  # >= threshold → reject
        }
        result = orch._run_filter_chain(_happy_signal())
        assert result["passed"] is False
        assert result["rejected_by"] == "resolution"

    def test_ambiguity_reason(self):
        orch = _make_orch(self.base)
        orch._resolution_cache[MARKET_ID] = {
            "market_id": MARKET_ID,
            "ambiguity_score": MAX_AMBIGUITY_SCORE,
        }
        result = orch._run_filter_chain(_happy_signal())
        assert result["reason"] == "high_ambiguity"

    def test_bundle_arb_skips_filter2(self):
        orch = _make_orch(self.base)
        # High ambiguity would normally reject — bundle_arb bypasses filter 2
        orch._resolution_cache[MARKET_ID] = {
            "market_id": MARKET_ID,
            "ambiguity_score": 10,
        }
        result = orch._run_filter_chain(_happy_signal(signal_type="bundle_arb"))
        assert "resolution" in result["filters_passed"]

    def test_no_resolution_data_rejected(self):
        orch = _make_orch(self.base)
        orch._resolution_cache.pop(MARKET_ID, None)
        result = orch._run_filter_chain(_happy_signal())
        assert result["passed"] is False
        assert result["rejected_by"] == "resolution"


# ===========================================================================
# Class 4: TestOtherFilters — supporting coverage
# ===========================================================================

class TestOtherFilters:
    """Filter 0 (data_quality) and filter 4 (kill_switch) edge cases."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.base = str(tmp_path)
        _setup_state(self.base)

    def test_filter0_no_price_data(self):
        orch = _make_orch(self.base)
        orch._price_cache.pop(MARKET_ID, None)
        result = orch._run_filter_chain(_happy_signal())
        assert result["passed"] is False
        assert result["rejected_by"] == "data_quality"

    def test_filter0_suspect_data(self):
        orch = _make_orch(self.base)
        orch._price_cache[MARKET_ID] = {
            "market_id": MARKET_ID,
            "data_status": "STALE",
            "yes_ask": 0.55,
            "no_ask": 0.45,
        }
        result = orch._run_filter_chain(_happy_signal())
        assert result["passed"] is False
        assert result["rejected_by"] == "data_quality"

    def test_filter4_kill_switch_blocked(self):
        orch = _make_orch(self.base, kill_switch=MockKillSwitch(allowed=False))
        result = orch._run_filter_chain(_happy_signal())
        assert result["passed"] is False
        assert result["rejected_by"] == "kill_switch"
