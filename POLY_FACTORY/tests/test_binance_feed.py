"""Tests for POLY_BINANCE_FEED — agents/poly_binance_feed.py"""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.poly_binance_feed import PolyBinanceFeed, STATE_FILE, DEFAULT_SYMBOLS


# --- Sample Binance API responses ---

SAMPLE_PRICE_RESPONSE = {
    "symbol": "BTCUSDT",
    "price": "98432.50",
}

SAMPLE_DEPTH_RESPONSE = {
    "lastUpdateId": 123456789,
    "bids": [
        ["98430.00", "1.20000"],
        ["98428.00", "0.80000"],
        ["98425.00", "2.50000"],
        ["98420.00", "1.10000"],
        ["98415.00", "0.30000"],
    ],
    "asks": [
        ["98435.00", "0.90000"],
        ["98437.00", "1.10000"],
        ["98440.00", "0.50000"],
        ["98445.00", "2.00000"],
        ["98450.00", "0.70000"],
    ],
}

SAMPLE_ETH_PRICE_RESPONSE = {
    "symbol": "ETHUSDT",
    "price": "3456.78",
}

SAMPLE_ETH_DEPTH_RESPONSE = {
    "lastUpdateId": 987654321,
    "bids": [
        ["3455.00", "10.00"],
        ["3454.00", "5.00"],
        ["3453.00", "8.00"],
        ["3452.00", "3.00"],
        ["3451.00", "1.00"],
    ],
    "asks": [
        ["3457.00", "7.00"],
        ["3458.00", "4.00"],
        ["3459.00", "6.00"],
        ["3460.00", "2.00"],
        ["3461.00", "1.00"],
    ],
}

SAMPLE_AGG_TRADE_MSG = {
    "e": "aggTrade",
    "s": "BTCUSDT",
    "p": "98432.50",
    "q": "0.15",
    "T": 1713624765123,
}

SAMPLE_DEPTH_WS_MSG = {
    "lastUpdateId": 123456789,
    "bids": [
        ["98430.00", "1.20"],
        ["98428.00", "0.80"],
        ["98425.00", "2.50"],
        ["98420.00", "1.10"],
        ["98415.00", "0.30"],
    ],
    "asks": [
        ["98435.00", "0.90"],
        ["98437.00", "1.10"],
        ["98440.00", "0.50"],
        ["98445.00", "2.00"],
        ["98450.00", "0.70"],
    ],
}


@pytest.fixture
def feed(tmp_path):
    """Create a PolyBinanceFeed with tmp_path."""
    return PolyBinanceFeed(base_path=str(tmp_path))


class TestBuildPayload:
    def test_format(self, feed):
        payload = feed._build_payload(
            symbol="BTCUSDT",
            price=98432.50,
            bids=[[98430, 1.2], [98428, 0.8], [98425, 2.5], [98420, 1.1], [98415, 0.3]],
            asks=[[98435, 0.9], [98437, 1.1], [98440, 0.5], [98445, 2.0], [98450, 0.7]],
            last_trade_qty=0.15,
        )

        assert payload["symbol"] == "BTCUSDT"
        assert payload["price"] == 98432.50
        assert len(payload["bids_top5"]) == 5
        assert len(payload["asks_top5"]) == 5
        assert payload["last_trade_qty"] == 0.15
        assert payload["data_status"] == "VALID"

    def test_truncates_to_5_levels(self, feed):
        bids = [[i, 1.0] for i in range(10)]
        asks = [[i, 1.0] for i in range(10)]
        payload = feed._build_payload("BTCUSDT", 100.0, bids, asks, 0.1)
        assert len(payload["bids_top5"]) == 5
        assert len(payload["asks_top5"]) == 5

    def test_data_status_always_valid(self, feed):
        payload = feed._build_payload("ETHUSDT", 3456.0, [], [], 0.0)
        assert payload["data_status"] == "VALID"


class TestFetchPrice:
    @patch.object(PolyBinanceFeed, "_http_get")
    def test_parses_response(self, mock_get, feed):
        mock_get.return_value = SAMPLE_PRICE_RESPONSE
        result = feed.fetch_price("BTCUSDT")

        assert result["symbol"] == "BTCUSDT"
        assert result["price"] == 98432.50
        assert isinstance(result["price"], float)

    @patch.object(PolyBinanceFeed, "_http_get")
    def test_calls_correct_url(self, mock_get, feed):
        mock_get.return_value = SAMPLE_PRICE_RESPONSE
        feed.fetch_price("BTCUSDT")
        url = mock_get.call_args[0][0]
        assert "ticker/price" in url
        assert "symbol=BTCUSDT" in url


class TestFetchOrderbook:
    @patch.object(PolyBinanceFeed, "_http_get")
    def test_parses_response(self, mock_get, feed):
        mock_get.return_value = SAMPLE_DEPTH_RESPONSE
        result = feed.fetch_orderbook("BTCUSDT", limit=5)

        assert len(result["bids"]) == 5
        assert len(result["asks"]) == 5
        assert result["bids"][0] == [98430.0, 1.2]
        assert result["asks"][0] == [98435.0, 0.9]
        assert isinstance(result["bids"][0][0], float)


class TestFetchSnapshot:
    @patch.object(PolyBinanceFeed, "_http_get")
    def test_combines_price_and_orderbook(self, mock_get, feed):
        def side_effect(url):
            if "ticker/price" in url:
                return SAMPLE_PRICE_RESPONSE
            elif "depth" in url:
                return SAMPLE_DEPTH_RESPONSE
            return {}

        mock_get.side_effect = side_effect
        payload = feed.fetch_snapshot("BTCUSDT")

        assert payload["symbol"] == "BTCUSDT"
        assert payload["price"] == 98432.50
        assert len(payload["bids_top5"]) == 5
        assert len(payload["asks_top5"]) == 5
        assert payload["data_status"] == "VALID"


class TestUpdate:
    def test_writes_state_file(self, feed, tmp_path):
        payload = feed._build_payload("BTCUSDT", 98432.50, [[98430, 1.2]], [[98435, 0.9]], 0.15)
        feed.update("BTCUSDT", payload)

        state = feed.store.read_json(STATE_FILE)
        assert state is not None
        assert "BTCUSDT" in state
        assert state["BTCUSDT"]["price"] == 98432.50

    def test_publishes_bus_event(self, feed):
        feed.bus.publish = MagicMock()
        payload = feed._build_payload("BTCUSDT", 98432.50, [], [], 0.15)
        feed.update("BTCUSDT", payload)

        feed.bus.publish.assert_called_once()
        args, kwargs = feed.bus.publish.call_args
        assert kwargs.get("topic", args[0] if args else None) == "feed:binance_update"
        assert kwargs.get("producer", args[1] if len(args) > 1 else None) == "POLY_BINANCE_FEED"

    def test_updates_last_update_time(self, feed):
        payload = feed._build_payload("BTCUSDT", 98432.50, [], [], 0.0)
        feed.update("BTCUSDT", payload)
        assert feed._last_update_time is not None
        assert time.time() - feed._last_update_time < 2

    def test_multiple_symbols_coexist(self, feed, tmp_path):
        btc = feed._build_payload("BTCUSDT", 98432.50, [], [], 0.15)
        eth = feed._build_payload("ETHUSDT", 3456.78, [], [], 1.5)

        feed.update("BTCUSDT", btc)
        feed.update("ETHUSDT", eth)

        state = feed.store.read_json(STATE_FILE)
        assert "BTCUSDT" in state
        assert "ETHUSDT" in state
        assert state["BTCUSDT"]["price"] == 98432.50
        assert state["ETHUSDT"]["price"] == 3456.78


class TestPollOnce:
    @patch.object(PolyBinanceFeed, "_http_get")
    def test_updates_all_symbols(self, mock_get, feed, tmp_path):
        def side_effect(url):
            if "BTCUSDT" in url and "ticker/price" in url:
                return SAMPLE_PRICE_RESPONSE
            elif "BTCUSDT" in url and "depth" in url:
                return SAMPLE_DEPTH_RESPONSE
            elif "ETHUSDT" in url and "ticker/price" in url:
                return SAMPLE_ETH_PRICE_RESPONSE
            elif "ETHUSDT" in url and "depth" in url:
                return SAMPLE_ETH_DEPTH_RESPONSE
            return {}

        mock_get.side_effect = side_effect
        results = feed.poll_once()

        assert "BTCUSDT" in results
        assert "ETHUSDT" in results
        assert results["BTCUSDT"]["price"] == 98432.50
        assert results["ETHUSDT"]["price"] == 3456.78

        state = feed.store.read_json(STATE_FILE)
        assert "BTCUSDT" in state
        assert "ETHUSDT" in state

    @patch.object(PolyBinanceFeed, "_http_get")
    def test_handles_partial_failure(self, mock_get, feed):
        def side_effect(url):
            if "BTCUSDT" in url and "ticker/price" in url:
                return SAMPLE_PRICE_RESPONSE
            elif "BTCUSDT" in url and "depth" in url:
                return SAMPLE_DEPTH_RESPONSE
            elif "ETHUSDT" in url:
                raise ConnectionError("API down")
            return {}

        mock_get.side_effect = side_effect
        results = feed.poll_once()

        assert "BTCUSDT" in results
        assert "ETHUSDT" not in results


class TestParseWebSocket:
    def test_parse_agg_trade(self, feed):
        result = feed.parse_agg_trade(SAMPLE_AGG_TRADE_MSG)
        assert result["symbol"] == "BTCUSDT"
        assert result["price"] == 98432.50
        assert result["last_trade_qty"] == 0.15

    def test_parse_depth(self, feed):
        result = feed.parse_depth(SAMPLE_DEPTH_WS_MSG)
        assert len(result["bids"]) == 5
        assert len(result["asks"]) == 5
        assert result["bids"][0] == [98430.0, 1.2]


class TestIsConnected:
    def test_false_when_no_updates(self, feed):
        assert feed.is_connected() is False

    def test_true_after_recent_update(self, feed):
        feed._last_update_time = time.time()
        assert feed.is_connected() is True

    def test_false_when_stale(self, feed):
        feed._last_update_time = time.time() - 200
        assert feed.is_connected() is False


class TestReconnectBackoff:
    def test_initial_backoff(self, feed):
        assert feed.calculate_reconnect_backoff() == 1

    def test_backoff_doubles(self, feed):
        feed.calculate_reconnect_backoff()  # 1
        assert feed.calculate_reconnect_backoff() == 2
        assert feed.calculate_reconnect_backoff() == 4

    def test_capped_at_max(self, feed):
        for _ in range(20):
            delay = feed.calculate_reconnect_backoff()
        assert delay <= feed.reconnect_max_backoff

    def test_resets(self, feed):
        for _ in range(5):
            feed.calculate_reconnect_backoff()
        feed.reset_reconnect_backoff()
        assert feed.calculate_reconnect_backoff() == 1


class TestStreamUrl:
    def test_default_symbols(self, feed):
        url = feed.get_ws_stream_url()
        assert "btcusdt@aggTrade" in url
        assert "btcusdt@depth20@100ms" in url
        assert "ethusdt@aggTrade" in url
        assert "ethusdt@depth20@100ms" in url

    def test_custom_symbols(self, tmp_path):
        feed = PolyBinanceFeed(base_path=str(tmp_path), symbols=["SOLUSDT"])
        url = feed.get_ws_stream_url()
        assert "solusdt@aggTrade" in url
        assert "btcusdt" not in url
