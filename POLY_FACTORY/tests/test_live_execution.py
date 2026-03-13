"""
Tests for POLY_LIVE_EXECUTION_ENGINE.

Coverage:
- Successful execution returns correct result dict
- execution_mode is always "live"
- tx_hash propagated from CLOB client
- All §7 schema fields present in result
- Strategy account debited after execution
- Trade persisted to live_trades_log.jsonl
- Retry on transient error then success
- Three retries exhausted → returns None
- No bus event published on total failure
- Audit logged on success and failure
- run_once polls execute:live and acks events
"""

import time
import pytest
from unittest.mock import patch, MagicMock

from core.poly_strategy_account import PolyStrategyAccount
from execution.poly_live_execution_engine import (
    PolyLiveExecutionEngine,
    CONSUMER_ID,
    FEE_RATE,
    MAX_RETRIES,
    LIVE_TRADES_LOG,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

STRATEGY    = "POLY_ARB_SCANNER"
ACCOUNT_ID  = "ACC_POLY_ARB_SCANNER"
MARKET_ID   = "0xabc123"
TX_HASH     = "0xdef456"
FILL_PRICE  = 0.55
GAS_COST    = 0.005
SIZE_EUR    = 30.0


def _mock_client(tx_hash=TX_HASH, fill_price=FILL_PRICE, gas_cost=GAS_COST):
    """Return a duck-typed mock CLOB client whose place_order() succeeds."""
    client = MagicMock()
    client.place_order.return_value = {
        "tx_hash":    tx_hash,
        "fill_price": fill_price,
        "gas_cost":   gas_cost,
    }
    return client


def _make_payload(direction="BUY_YES", size_eur=SIZE_EUR):
    """Build an execute:live payload dict."""
    return {
        "execution_mode":    "live",
        "strategy":          STRATEGY,
        "account_id":        ACCOUNT_ID,
        "market_id":         MARKET_ID,
        "platform":          "polymarket",
        "direction":         direction,
        "size_eur":          size_eur,
        "tranches":          [{"size": size_eur, "price_limit": 0.55}],
        "slippage_estimated": 0.003,
    }


def _create_account(tmp_path):
    """Create a funded strategy account for ACCOUNT_ID."""
    PolyStrategyAccount.create(
        strategy=STRATEGY,
        platform="polymarket",
        initial_capital=1000.0,
        base_path=str(tmp_path),
    )


@pytest.fixture
def engine(tmp_path):
    """Engine with injected mock client and a pre-funded strategy account."""
    _create_account(tmp_path)
    return PolyLiveExecutionEngine(
        base_path=str(tmp_path),
        clob_client=_mock_client(),
    )


# ---------------------------------------------------------------------------
# Execution success
# ---------------------------------------------------------------------------

def test_successful_execution_returns_result(engine):
    result = engine.execute(_make_payload())
    assert result is not None
    assert isinstance(result, dict)


def test_execution_mode_is_live(engine):
    result = engine.execute(_make_payload())
    assert result["execution_mode"] == "live"


def test_tx_hash_in_result(engine):
    result = engine.execute(_make_payload())
    assert result["tx_hash"] == TX_HASH


def test_all_payload_fields_present(engine):
    """All fields required by the §7 trade:live_executed schema must be present."""
    result = engine.execute(_make_payload())
    required = {
        "trade_id", "execution_mode", "strategy", "account_id",
        "market_id", "platform", "direction",
        "fill_price", "slippage_actual", "size_eur",
        "fees", "gas_cost", "tx_hash", "execution_time_ms",
    }
    assert required.issubset(result.keys())


def test_fill_price_from_clob_client(engine):
    result = engine.execute(_make_payload())
    assert result["fill_price"] == pytest.approx(FILL_PRICE)


def test_fees_computed_correctly(engine):
    result = engine.execute(_make_payload())
    expected_fees = SIZE_EUR * FEE_RATE
    assert result["fees"] == pytest.approx(expected_fees, rel=1e-6)


# ---------------------------------------------------------------------------
# Account & persistence
# ---------------------------------------------------------------------------

def test_account_debited_after_execution(tmp_path):
    _create_account(tmp_path)
    engine = PolyLiveExecutionEngine(
        base_path=str(tmp_path),
        clob_client=_mock_client(),
    )
    before = PolyStrategyAccount.load(ACCOUNT_ID, str(tmp_path)).data["capital"]["available"]
    engine.execute(_make_payload())
    after = PolyStrategyAccount.load(ACCOUNT_ID, str(tmp_path)).data["capital"]["available"]
    expected_debit = SIZE_EUR + SIZE_EUR * FEE_RATE
    assert before - after == pytest.approx(expected_debit, rel=1e-6)


def test_trade_logged_to_file(tmp_path):
    _create_account(tmp_path)
    engine = PolyLiveExecutionEngine(
        base_path=str(tmp_path),
        clob_client=_mock_client(),
    )
    engine.execute(_make_payload())
    records = engine.store.read_jsonl(LIVE_TRADES_LOG)
    assert len(records) == 1
    assert records[0]["market_id"] == MARKET_ID
    assert records[0]["execution_mode"] == "live"


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

def test_retry_on_transient_error_then_success(tmp_path):
    _create_account(tmp_path)
    client = MagicMock()
    # Fail once, then succeed
    client.place_order.side_effect = [
        TimeoutError("network timeout"),
        {"tx_hash": TX_HASH, "fill_price": FILL_PRICE, "gas_cost": GAS_COST},
    ]
    engine = PolyLiveExecutionEngine(base_path=str(tmp_path), clob_client=client)
    with patch("time.sleep"):
        result = engine.execute(_make_payload())
    assert result is not None
    assert result["tx_hash"] == TX_HASH
    assert client.place_order.call_count == 2


def test_three_retries_exhausted_returns_none(tmp_path):
    _create_account(tmp_path)
    client = MagicMock()
    client.place_order.side_effect = TimeoutError("network timeout")
    engine = PolyLiveExecutionEngine(base_path=str(tmp_path), clob_client=client)
    with patch("time.sleep"):
        result = engine.execute(_make_payload())
    assert result is None
    assert client.place_order.call_count == MAX_RETRIES


def test_no_bus_event_on_failure(tmp_path):
    _create_account(tmp_path)
    client = MagicMock()
    client.place_order.side_effect = TimeoutError("network timeout")
    engine = PolyLiveExecutionEngine(base_path=str(tmp_path), clob_client=client)
    with patch("time.sleep"):
        engine.execute(_make_payload())
    events = engine.bus.poll("test_consumer", topics=["trade:live_executed"])
    assert len(events) == 0


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def test_audit_logged_on_success(engine):
    engine.execute(_make_payload())
    events = engine.audit.read_events()
    topics = [e["topic"] for e in events]
    assert "trade:live_executed" in topics


def test_audit_logged_on_failure(tmp_path):
    _create_account(tmp_path)
    client = MagicMock()
    client.place_order.side_effect = TimeoutError("network timeout")
    engine = PolyLiveExecutionEngine(base_path=str(tmp_path), clob_client=client)
    with patch("time.sleep"):
        engine.execute(_make_payload())
    events = engine.audit.read_events()
    topics = [e["topic"] for e in events]
    assert "trade:live_failed" in topics


# ---------------------------------------------------------------------------
# run_once / bus integration
# ---------------------------------------------------------------------------

def test_run_once_polls_execute_live(tmp_path):
    _create_account(tmp_path)
    engine = PolyLiveExecutionEngine(
        base_path=str(tmp_path),
        clob_client=_mock_client(),
    )
    engine.bus.publish("execute:live", "POLY_EXECUTION_ROUTER", _make_payload())
    results = engine.run_once()
    assert len(results) == 1
    assert results[0] is not None
    assert results[0]["execution_mode"] == "live"


def test_run_once_acks_event(tmp_path):
    _create_account(tmp_path)
    engine = PolyLiveExecutionEngine(
        base_path=str(tmp_path),
        clob_client=_mock_client(),
    )
    engine.bus.publish("execute:live", "POLY_EXECUTION_ROUTER", _make_payload())
    first = engine.run_once()
    assert len(first) == 1
    second = engine.run_once()
    assert len(second) == 0
