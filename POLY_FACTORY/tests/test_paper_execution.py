"""
Tests for POLY_PAPER_EXECUTION_ENGINE (POLY-017).
"""

import json
import os
import pytest

from core.poly_strategy_account import PolyStrategyAccount
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from execution.poly_paper_execution_engine import (
    PolyPaperExecutionEngine,
    FEE_RATE,
    PAPER_TRADES_LOG,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(
    strategy="POLY_ARB_SCANNER",
    account_id="ACC_POLY_ARB_SCANNER",
    market_id="0xabc",
    platform="polymarket",
    direction="BUY_YES_AND_NO",
    size_eur=28.5,
    expected_fill_price=0.471,
    slippage_estimated=0.003,
):
    return {
        "execution_mode": "paper",
        "strategy": strategy,
        "account_id": account_id,
        "market_id": market_id,
        "platform": platform,
        "direction": direction,
        "size_eur": size_eur,
        "tranches": [{"size": size_eur / 2, "price_limit": 0.48}],
        "expected_fill_price": expected_fill_price,
        "slippage_estimated": slippage_estimated,
    }


@pytest.fixture
def engine(tmp_path):
    """Create an engine with a pre-created PolyStrategyAccount."""
    base = str(tmp_path)
    PolyStrategyAccount.create(
        strategy="POLY_ARB_SCANNER",
        platform="polymarket",
        base_path=base,
    )
    return PolyPaperExecutionEngine(base_path=base)


# ---------------------------------------------------------------------------
# Safety test
# ---------------------------------------------------------------------------

def test_no_py_clob_import():
    """The paper engine must never import py-clob-client."""
    src_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "execution",
        "poly_paper_execution_engine.py",
    )
    with open(src_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "py_clob_client" not in content
    assert "py-clob-client" not in content


# ---------------------------------------------------------------------------
# Execute tests
# ---------------------------------------------------------------------------

def test_execute_returns_result_dict(engine):
    result = engine.execute(_make_payload())
    assert isinstance(result, dict)


def test_execute_result_has_all_fields(engine):
    result = engine.execute(_make_payload())
    required = {
        "trade_id", "execution_mode", "strategy", "account_id",
        "market_id", "platform", "direction", "fill_price",
        "slippage_actual", "size_eur", "fees", "gas_cost",
        "tx_hash", "execution_time_ms",
    }
    assert required.issubset(result.keys())


def test_execute_trade_id_format(engine):
    result = engine.execute(_make_payload())
    assert result["trade_id"].startswith("TRD_")


def test_execute_fill_price_includes_slippage(engine):
    payload = _make_payload(expected_fill_price=0.471, slippage_estimated=0.003)
    result = engine.execute(payload)
    assert result["fill_price"] > payload["expected_fill_price"]


def test_execute_slippage_from_market_structure(engine):
    """When market_structure.json has an entry, slippage_actual = slippage_1k."""
    store = DataStore = PolyDataStore(base_path=engine.base_path)
    store.write_json("feeds/market_structure.json", {
        "0xabc": {"slippage_1k": 0.007, "spread": 0.01}
    })
    payload = _make_payload(market_id="0xabc", slippage_estimated=0.003)
    result = engine.execute(payload)
    assert abs(result["slippage_actual"] - 0.007) < 1e-9


def test_execute_slippage_fallback(engine):
    """When market_structure has no entry, slippage_actual = slippage_estimated."""
    store = PolyDataStore(base_path=engine.base_path)
    store.write_json("feeds/market_structure.json", {})
    payload = _make_payload(market_id="0xunknown", slippage_estimated=0.005)
    result = engine.execute(payload)
    assert abs(result["slippage_actual"] - 0.005) < 1e-9


def test_execute_fees_computed(engine):
    payload = _make_payload(size_eur=100.0)
    result = engine.execute(payload)
    assert abs(result["fees"] - 100.0 * FEE_RATE) < 1e-9


def test_execute_gas_cost_zero(engine):
    result = engine.execute(_make_payload())
    assert result["gas_cost"] == 0.0


def test_execute_tx_hash_none(engine):
    result = engine.execute(_make_payload())
    assert result["tx_hash"] is None


def test_execute_updates_account(engine):
    from core.poly_strategy_account import PolyStrategyAccount
    account_before = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", engine.base_path)
    capital_before = account_before.data["capital"]["current"]

    payload = _make_payload(size_eur=50.0)
    result = engine.execute(payload)

    account_after = PolyStrategyAccount.load("ACC_POLY_ARB_SCANNER", engine.base_path)
    capital_after = account_after.data["capital"]["current"]

    expected_debit = 50.0 + result["fees"]
    assert abs(capital_before - capital_after - expected_debit) < 1e-6


def test_execute_appends_to_log(engine):
    store = PolyDataStore(base_path=engine.base_path)
    before = store.read_jsonl(PAPER_TRADES_LOG)
    engine.execute(_make_payload())
    after = store.read_jsonl(PAPER_TRADES_LOG)
    assert len(after) == len(before) + 1


def test_execute_log_entry_fields(engine):
    store = PolyDataStore(base_path=engine.base_path)
    engine.execute(_make_payload())
    entries = store.read_jsonl(PAPER_TRADES_LOG)
    entry = entries[-1]
    for field in ("trade_id", "strategy", "fill_price", "size_eur", "fees"):
        assert field in entry


def test_execute_publishes_bus_event(engine):
    store = PolyDataStore(base_path=engine.base_path)
    engine.execute(_make_payload())
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "trade:paper_executed" in topics


def test_execute_audit_log_entry(engine):
    from core.poly_audit_log import PolyAuditLog
    from datetime import datetime, timezone
    engine.execute(_make_payload())
    audit = PolyAuditLog(base_path=engine.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "trade:paper_executed" in topics


# ---------------------------------------------------------------------------
# run_once test
# ---------------------------------------------------------------------------

def test_run_once_processes_execute_paper_event(engine):
    bus = PolyEventBus(base_path=engine.base_path)
    payload = _make_payload()
    bus.publish(topic="execute:paper", producer="TEST", payload=payload)

    results = engine.run_once()

    assert len(results) == 1
    assert results[0]["trade_id"].startswith("TRD_")

    # Event should be acked — run_once again returns nothing new
    results2 = engine.run_once()
    assert len(results2) == 0
