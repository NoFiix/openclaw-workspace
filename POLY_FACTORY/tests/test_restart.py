"""
POLY-T07 — Restart and recovery tests.

Three required scenarios:
  1. kill PM2 → restart auto          (POLY_HEARTBEAT)
  2. crash mid-trade → no duplicate   (POLY_PAPER_EXECUTION_ENGINE + bus idempotence)
  3. restart → feeds reprennent < 60s (POLY_BINANCE_FEED)
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from agents.poly_binance_feed import PolyBinanceFeed
from agents.poly_heartbeat import PolyHeartbeat, MAX_RESTARTS
from core.poly_event_bus import PolyEventBus
from core.poly_strategy_account import PolyStrategyAccount
from execution.poly_paper_execution_engine import PolyPaperExecutionEngine, PAPER_TRADES_LOG


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRATEGY = "POLY_ARB_SCANNER"
MARKET_ID = "market-restart-001"
PLATFORM = "polymarket"
AGENT_NAME = "POLY_BINANCE_FEED"
EXPECTED_FREQ_S = 30.0  # so stale after 60s; never-pinged → immediately stale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_account(base):
    return PolyStrategyAccount.create(STRATEGY, PLATFORM, str(base))


def _make_execute_payload():
    """Minimal valid execute:paper payload."""
    return {
        "strategy": STRATEGY,
        "account_id": f"ACC_{STRATEGY}",
        "market_id": MARKET_ID,
        "platform": PLATFORM,
        "direction": "BUY_YES",
        "size_eur": 20.0,
        "expected_fill_price": 0.60,
        "slippage_estimated": 0.005,
    }


def _make_http_mock():
    """Return a side_effect function for _http_get that dispatches on URL."""
    def _http_get(url):
        if "/ticker/price" in url:
            # Extract symbol from URL query param
            symbol = url.split("symbol=")[-1].split("&")[0]
            return {"symbol": symbol, "price": "50000.00"}
        if "/depth" in url:
            return {
                "bids": [["49990.00", "0.5"]],
                "asks": [["50010.00", "0.5"]],
            }
        raise ConnectionError(f"Unexpected URL: {url}")
    return _http_get


# ---------------------------------------------------------------------------
# Scenario 1 — "kill PM2 → restart auto"  (POLY_HEARTBEAT)
# ---------------------------------------------------------------------------

class TestHeartbeatRestart:
    """PolyHeartbeat detects stale agent, calls restart_fn, disables after MAX_RESTARTS."""

    def _hb(self, tmp_path, restart_fn=None):
        hb = PolyHeartbeat(base_path=str(tmp_path), restart_fn=restart_fn)
        hb.register(AGENT_NAME, expected_freq_s=EXPECTED_FREQ_S)
        return hb

    def test_stale_agent_triggers_restart(self, tmp_path):
        restart_fn = MagicMock(return_value=True)
        hb = self._hb(tmp_path, restart_fn)
        result = hb.run_once()
        assert AGENT_NAME in result["restarted"]

    def test_restart_fn_called_with_correct_name(self, tmp_path):
        restart_fn = MagicMock(return_value=True)
        hb = self._hb(tmp_path, restart_fn)
        hb.run_once()
        restart_fn.assert_called_once_with(AGENT_NAME)

    def test_max_restarts_disables_agent(self, tmp_path):
        restart_fn = MagicMock(return_value=True)
        hb = self._hb(tmp_path, restart_fn)
        result = None
        for _ in range(MAX_RESTARTS):
            result = hb.run_once()
        assert result["disabled"]
        assert hb._state["agents"][AGENT_NAME]["status"] == "disabled"

    def test_disabled_agent_not_restarted_again(self, tmp_path):
        restart_fn = MagicMock(return_value=True)
        hb = self._hb(tmp_path, restart_fn)
        for _ in range(MAX_RESTARTS):
            hb.run_once()
        call_count_after_disable = restart_fn.call_count
        # One more run_once — disabled agent should be skipped
        hb.run_once()
        assert restart_fn.call_count == call_count_after_disable

    def test_agent_disabled_bus_event_published(self, tmp_path):
        restart_fn = MagicMock(return_value=True)
        hb = self._hb(tmp_path, restart_fn)
        for _ in range(MAX_RESTARTS):
            hb.run_once()
        events = hb.bus.poll("TEST_CONSUMER", topics=["system:agent_disabled"])
        assert any(
            e["payload"]["agent"] == AGENT_NAME for e in events
        )

    def test_restart_count_persists_across_instances(self, tmp_path):
        restart_fn = MagicMock(return_value=True)
        hb1 = self._hb(tmp_path, restart_fn)
        hb1.run_once()
        # Simulate restart: new instance, same base_path
        hb2 = PolyHeartbeat(base_path=str(tmp_path))
        assert hb2._state["agents"][AGENT_NAME]["restart_count"] == 1


# ---------------------------------------------------------------------------
# Scenario 2 — "crash mid-trade → no duplicate trade"
# ---------------------------------------------------------------------------

class TestNoDuplicateTradeOnRestart:
    """Bus idempotence prevents re-executing an already-processed trade on restart."""

    def _setup(self, tmp_path):
        _create_account(tmp_path)
        bus = PolyEventBus(base_path=str(tmp_path))
        bus.publish(
            topic="execute:paper",
            producer="POLY_ARB_SCANNER",
            payload=_make_execute_payload(),
        )
        return bus

    def test_acked_event_not_replayed_after_restart(self, tmp_path):
        self._setup(tmp_path)
        engine1 = PolyPaperExecutionEngine(base_path=str(tmp_path))
        results1 = engine1.run_once()
        assert len(results1) == 1

        # Simulate restart with a fresh engine instance (same state dir)
        engine2 = PolyPaperExecutionEngine(base_path=str(tmp_path))
        results2 = engine2.run_once()
        assert results2 == []

    def test_paper_trade_log_has_exactly_one_entry(self, tmp_path):
        self._setup(tmp_path)
        engine1 = PolyPaperExecutionEngine(base_path=str(tmp_path))
        engine1.run_once()

        engine2 = PolyPaperExecutionEngine(base_path=str(tmp_path))
        engine2.run_once()

        log = engine1.store.read_jsonl(PAPER_TRADES_LOG)
        assert len(log) == 1

    def test_unacked_event_replayed_after_restart(self, tmp_path):
        """Simulate crash before ack: execute() called but ack() never called."""
        _create_account(tmp_path)
        bus = PolyEventBus(base_path=str(tmp_path))
        evt_envelope = bus.publish(
            topic="execute:paper",
            producer="POLY_ARB_SCANNER",
            payload=_make_execute_payload(),
        )

        engine1 = PolyPaperExecutionEngine(base_path=str(tmp_path))
        # Call execute directly — no ack (simulates crash between execute and ack)
        engine1.execute(_make_execute_payload())

        # Restart: new engine sees the event as unprocessed
        engine2 = PolyPaperExecutionEngine(base_path=str(tmp_path))
        results2 = engine2.run_once()
        assert len(results2) == 1

    def test_acked_ids_persisted_to_disk(self, tmp_path):
        """bus.ack() writes to processed_events.jsonl; a different consumer can still see the event (pub/sub)."""
        _create_account(tmp_path)
        bus1 = PolyEventBus(base_path=str(tmp_path))
        envelope = bus1.publish(
            topic="execute:paper",
            producer="POLY_ARB_SCANNER",
            payload=_make_execute_payload(),
        )
        event_id = envelope["event_id"]

        # Ack via bus1 as CONSUMER_A
        bus1.ack("CONSUMER_A", event_id)

        # New bus instance — simulates restart.
        # CONSUMER_B should still see the event (pub/sub: per-consumer filtering).
        bus2 = PolyEventBus(base_path=str(tmp_path))
        events = bus2.poll("CONSUMER_B", topics=["execute:paper"])
        found_ids = [e["event_id"] for e in events]
        assert event_id in found_ids

        # But CONSUMER_A should NOT see it again (idempotence)
        events_a = bus2.poll("CONSUMER_A", topics=["execute:paper"])
        found_ids_a = [e["event_id"] for e in events_a]
        assert event_id not in found_ids_a


# ---------------------------------------------------------------------------
# Scenario 3 — "restart → feeds reprennent < 60s"  (POLY_BINANCE_FEED)
# ---------------------------------------------------------------------------

class TestFeedResumesAfterRestart:
    """PolyBinanceFeed becomes operational after a single poll_once() following restart."""

    def _feed(self, tmp_path, symbols=None):
        return PolyBinanceFeed(
            base_path=str(tmp_path),
            symbols=symbols or ["BTCUSDT"],
        )

    def test_feed_not_connected_on_fresh_init(self, tmp_path):
        feed = self._feed(tmp_path)
        assert feed.is_connected() is False

    def test_poll_once_completes_quickly(self, tmp_path):
        feed = self._feed(tmp_path)
        with patch.object(feed, "_http_get", side_effect=_make_http_mock()):
            t0 = time.monotonic()
            feed.poll_once()
            elapsed = time.monotonic() - t0
        assert elapsed < 1.0  # well within the 60s budget

    def test_state_file_written_after_poll(self, tmp_path):
        feed = self._feed(tmp_path)
        with patch.object(feed, "_http_get", side_effect=_make_http_mock()):
            feed.poll_once()
        data = feed.store.read_json("feeds/binance_raw.json")
        assert data is not None
        assert "BTCUSDT" in data

    def test_restarted_feed_becomes_connected_after_single_poll(self, tmp_path):
        # First instance writes state
        feed1 = self._feed(tmp_path)
        with patch.object(feed1, "_http_get", side_effect=_make_http_mock()):
            feed1.poll_once()

        # Simulate restart: new instance, same base_path
        feed2 = self._feed(tmp_path)
        assert feed2.is_connected() is False  # _last_update_time not loaded from disk

        with patch.object(feed2, "_http_get", side_effect=_make_http_mock()):
            feed2.poll_once()

        assert feed2.is_connected() is True

    def test_state_file_survives_restart(self, tmp_path):
        """State written by feed1 is readable after feed2 starts."""
        feed1 = self._feed(tmp_path)
        with patch.object(feed1, "_http_get", side_effect=_make_http_mock()):
            feed1.poll_once()

        # Simulate restart with fresh feed instance
        feed2 = self._feed(tmp_path)
        data = feed2.store.read_json("feeds/binance_raw.json")
        assert data is not None
        assert "BTCUSDT" in data
        assert "price" in data["BTCUSDT"]
