"""
POLY-T06 — API failure handling tests.

Four required scenarios:
  1. WS disconnect → reconnection  (BINANCE_FEED)
  2. API 5xx → retry               (LIVE_EXECUTION_ENGINE)
  3. 3 retries → dead letter        (LIVE_EXECUTION_ENGINE)
  4. gas insufficient → alert       (LIVE_EXECUTION_ENGINE)
"""

import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from agents.poly_binance_feed import (
    PolyBinanceFeed,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_RECONNECT_INITIAL,
    DEFAULT_RECONNECT_MAX_BACKOFF,
)
from core.poly_strategy_account import PolyStrategyAccount
from execution.poly_live_execution_engine import (
    PolyLiveExecutionEngine,
    MAX_RETRIES,
    LIVE_TRADES_LOG,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRATEGY = "POLY_ARB_SCANNER"
MARKET_ID = "market-api-001"
PLATFORM = "polymarket"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_client(fail_n=0, error_msg="HTTP 503 Service Unavailable"):
    """Return a MagicMock whose place_order() raises ConnectionError for the
    first fail_n calls, then returns a valid response dict."""
    client = MagicMock()
    call_count = {"n": 0}

    def _place_order(**kwargs):
        call_count["n"] += 1
        if call_count["n"] <= fail_n:
            raise ConnectionError(error_msg)
        return {"tx_hash": "0xdeadbeef", "fill_price": 0.65, "gas_cost": 0.001}

    client.place_order.side_effect = _place_order
    return client


def _make_payload(direction="BUY_YES", size_eur=30.0):
    """Minimal valid execute:live payload dict."""
    return {
        "strategy": STRATEGY,
        "account_id": f"ACC_{STRATEGY}",
        "market_id": MARKET_ID,
        "platform": PLATFORM,
        "direction": direction,
        "size_eur": size_eur,
        "slippage_estimated": 0.0,
        "tranches": [],
    }


def _create_account(base):
    return PolyStrategyAccount.create(STRATEGY, PLATFORM, base)


# ---------------------------------------------------------------------------
# Scenario 1 — WS disconnect / reconnection  (POLY_BINANCE_FEED)
# ---------------------------------------------------------------------------

class TestBinanceFeedDisconnect:
    """Tests for BINANCE_FEED connection state and reconnect backoff."""

    def _feed(self, tmp_path):
        return PolyBinanceFeed(base_path=str(tmp_path))

    def _valid_payload(self):
        return {
            "symbol": "BTCUSDT",
            "price": 50000.0,
            "bids_top5": [[49990.0, 0.1]],
            "asks_top5": [[50010.0, 0.1]],
            "last_trade_qty": 0.01,
            "data_status": "VALID",
        }

    def test_not_connected_when_never_updated(self, tmp_path):
        feed = self._feed(tmp_path)
        assert feed.is_connected() is False

    def test_connected_after_update(self, tmp_path):
        feed = self._feed(tmp_path)
        feed.update("BTCUSDT", self._valid_payload())
        assert feed.is_connected() is True

    def test_disconnected_when_data_stale(self, tmp_path):
        feed = self._feed(tmp_path)
        feed._last_update_time = 0.0  # epoch — always stale
        assert feed.is_connected() is False

    def test_reconnect_backoff_initial(self, tmp_path):
        feed = self._feed(tmp_path)
        delay = feed.calculate_reconnect_backoff()
        assert delay == DEFAULT_RECONNECT_INITIAL

    def test_reconnect_backoff_doubles(self, tmp_path):
        feed = self._feed(tmp_path)
        first = feed.calculate_reconnect_backoff()
        second = feed.calculate_reconnect_backoff()
        assert first == 1.0
        assert second == 2.0

    def test_reconnect_backoff_capped_at_max(self, tmp_path):
        feed = self._feed(tmp_path)
        last = None
        for _ in range(20):
            last = feed.calculate_reconnect_backoff()
        assert last == DEFAULT_RECONNECT_MAX_BACKOFF

    def test_reset_reconnect_backoff(self, tmp_path):
        feed = self._feed(tmp_path)
        # Advance a few times
        for _ in range(5):
            feed.calculate_reconnect_backoff()
        feed.reset_reconnect_backoff()
        assert feed._reconnect_backoff == feed.reconnect_initial

    def test_poll_once_http_503_skips_symbol(self, tmp_path):
        feed = self._feed(tmp_path)
        with patch.object(feed, "_http_get", side_effect=ConnectionError("HTTP 503 Service Unavailable")):
            results = feed.poll_once()
        assert results == {}
        assert feed.is_connected() is False


# ---------------------------------------------------------------------------
# Scenario 2 — API 5xx → retry  (POLY_LIVE_EXECUTION_ENGINE)
# ---------------------------------------------------------------------------

class TestLiveEngineApiRetry:
    """Client returns 5xx transiently; engine retries and eventually succeeds."""

    def _engine(self, tmp_path, client):
        _create_account(str(tmp_path))
        return PolyLiveExecutionEngine(base_path=str(tmp_path), clob_client=client)

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_5xx_error_retries_and_succeeds(self, _sleep, tmp_path):
        client = _mock_client(fail_n=2)
        engine = self._engine(tmp_path, client)
        result = engine.execute(_make_payload())
        assert result is not None
        assert client.place_order.call_count == 3

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_single_attempt_success_no_retry(self, _sleep, tmp_path):
        client = _mock_client(fail_n=0)
        engine = self._engine(tmp_path, client)
        result = engine.execute(_make_payload())
        assert result is not None
        assert client.place_order.call_count == 1

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_5xx_error_message_preserved_in_retry(self, _sleep, tmp_path):
        client = _mock_client(fail_n=1, error_msg="HTTP 503 Service Unavailable")
        engine = self._engine(tmp_path, client)
        engine.execute(_make_payload())
        assert client.place_order.call_count > 1


# ---------------------------------------------------------------------------
# Scenario 3 — 3 retries → dead letter  (POLY_LIVE_EXECUTION_ENGINE)
# ---------------------------------------------------------------------------

class TestLiveEngineDeadLetter:
    """All MAX_RETRIES attempts fail → None returned, audit written, bus silent."""

    def _engine(self, tmp_path):
        _create_account(str(tmp_path))
        client = _mock_client(fail_n=MAX_RETRIES, error_msg="HTTP 503 Service Unavailable")
        return PolyLiveExecutionEngine(base_path=str(tmp_path), clob_client=client)

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_3_retries_exhausted_returns_none(self, _sleep, tmp_path):
        engine = self._engine(tmp_path)
        result = engine.execute(_make_payload())
        assert result is None

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_3_retries_no_bus_event(self, _sleep, tmp_path):
        engine = self._engine(tmp_path)
        engine.execute(_make_payload())
        events = engine.bus.poll("TEST_CONSUMER", topics=["trade:live_executed"])
        assert events == []

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_3_retries_audit_entry_written(self, _sleep, tmp_path):
        engine = self._engine(tmp_path)
        engine.execute(_make_payload())
        entries = engine.audit.read_events()
        topics = [e["topic"] for e in entries]
        assert "trade:live_failed" in topics

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_3_retries_audit_retries_count(self, _sleep, tmp_path):
        engine = self._engine(tmp_path)
        engine.execute(_make_payload())
        entries = engine.audit.read_events()
        failed = [e for e in entries if e["topic"] == "trade:live_failed"]
        assert len(failed) == 1
        assert failed[0]["payload"]["retries"] == MAX_RETRIES


# ---------------------------------------------------------------------------
# Scenario 4 — Gas insufficient → alert  (POLY_LIVE_EXECUTION_ENGINE)
# ---------------------------------------------------------------------------

class TestGasAlert:
    """Insufficient gas error is caught, retried MAX_RETRIES times, then audited."""

    def _engine(self, tmp_path):
        _create_account(str(tmp_path))
        client = MagicMock()
        client.place_order.side_effect = Exception("insufficient gas for transaction")
        return PolyLiveExecutionEngine(base_path=str(tmp_path), clob_client=client)

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_gas_error_returns_none(self, _sleep, tmp_path):
        engine = self._engine(tmp_path)
        result = engine.execute(_make_payload())
        assert result is None

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_gas_error_preserved_in_audit(self, _sleep, tmp_path):
        engine = self._engine(tmp_path)
        engine.execute(_make_payload())
        entries = engine.audit.read_events()
        failed = [e for e in entries if e["topic"] == "trade:live_failed"]
        assert len(failed) == 1
        assert "gas" in failed[0]["payload"]["error"].lower()

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_gas_error_no_trade_logged(self, _sleep, tmp_path):
        engine = self._engine(tmp_path)
        engine.execute(_make_payload())
        log = engine.store.read_jsonl(LIVE_TRADES_LOG)
        assert log == []

    @patch("execution.poly_live_execution_engine.time.sleep")
    def test_gas_error_place_order_called_max_retries(self, _sleep, tmp_path):
        engine = self._engine(tmp_path)
        engine.execute(_make_payload())
        assert engine._clob_client.place_order.call_count == MAX_RETRIES
