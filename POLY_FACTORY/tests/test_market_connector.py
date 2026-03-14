"""Tests for POLY_MARKET_CONNECTOR — agents/poly_market_connector.py + connectors/connector_polymarket.py"""

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.poly_market_connector import PolyMarketConnector
from connectors.connector_polymarket import ConnectorPolymarket, PRICES_STATE_FILE


# --- Sample Gamma API responses for mocking ---

SAMPLE_MARKETS_RESPONSE = [
    {
        "condition_id": "0xabc123",
        "question": "Will BTC reach 100k by end of March?",
        "active": True,
        "end_date_iso": "2026-03-31T23:59:59Z",
        "slug": "btc-100k-march",
        "volume_24hr": 50000,
        "tokens": [
            {"outcome": "Yes", "price": 0.62},
            {"outcome": "No", "price": 0.38},
        ],
    },
    {
        "condition_id": "0xdef456",
        "question": "Will ETH flip BTC?",
        "active": True,
        "end_date_iso": "2026-06-30T23:59:59Z",
        "slug": "eth-flip-btc",
        "volume_24hr": 12000,
        "tokens": [
            {"outcome": "Yes", "price": 0.05},
            {"outcome": "No", "price": 0.95},
        ],
    },
]

SAMPLE_MARKET_DETAIL = {
    "condition_id": "0xabc123",
    "question": "Will BTC reach 100k?",
    "active": True,
    "volume_24hr": 50000,
    "resolved": False,
    "tokens": [
        {"outcome": "Yes", "price": 0.62, "ask": 0.63, "bid": 0.61},
        {"outcome": "No", "price": 0.39, "ask": 0.40, "bid": 0.38},
    ],
}

SAMPLE_RESOLVED_MARKET = {
    "condition_id": "0xresolved",
    "resolved": True,
    "outcome": "Yes",
    "resolved_at": "2026-03-10T12:00:00Z",
    "tokens": [],
}


@pytest.fixture
def connector(tmp_path):
    """Create a ConnectorPolymarket with tmp_path and default config."""
    return ConnectorPolymarket(
        base_path=str(tmp_path),
        config={
            "gamma_api_url": "https://gamma-api.polymarket.com",
            "clob_ws_url": "wss://ws-subscriptions-clob.polymarket.com/ws/market",
            "ping_interval_s": 60,
            "reconnect_initial_s": 1,
            "reconnect_max_backoff_s": 30,
            "connection_timeout_s": 120,
        },
    )


class TestABCInterface:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            PolyMarketConnector()

    def test_connector_is_instance_of_abc(self, connector):
        assert isinstance(connector, PolyMarketConnector)

    def test_abc_requires_all_methods(self):
        """A partial implementation should fail to instantiate."""

        class IncompleteConnector(PolyMarketConnector):
            def get_markets(self, filter_active=True):
                return []

        with pytest.raises(TypeError):
            IncompleteConnector()


class TestGetPlatform:
    def test_returns_polymarket(self, connector):
        assert connector.get_platform() == "polymarket"


class TestGetMarkets:
    @patch.object(ConnectorPolymarket, "_http_get")
    def test_parses_response(self, mock_get, connector):
        mock_get.return_value = SAMPLE_MARKETS_RESPONSE
        markets = connector.get_markets()

        assert len(markets) == 2
        assert markets[0]["market_id"] == "0xabc123"
        assert markets[0]["question"] == "Will BTC reach 100k by end of March?"
        assert markets[0]["platform"] == "polymarket"
        assert markets[0]["active"] is True
        assert markets[0]["volume_24h"] == 50000

    @patch.object(ConnectorPolymarket, "_http_get")
    def test_empty_response(self, mock_get, connector):
        mock_get.return_value = []
        markets = connector.get_markets()
        assert markets == []

    @patch.object(ConnectorPolymarket, "_http_get")
    def test_calls_correct_url(self, mock_get, connector):
        mock_get.return_value = []
        connector.get_markets(filter_active=True)
        url = mock_get.call_args[0][0]
        assert "active=true" in url
        assert "closed=false" in url


class TestGetOrderbook:
    @patch.object(ConnectorPolymarket, "_http_get")
    def test_format(self, mock_get, connector):
        mock_get.return_value = SAMPLE_MARKET_DETAIL
        ob = connector.get_orderbook("0xabc123")

        assert ob["market_id"] == "0xabc123"
        assert ob["platform"] == "polymarket"
        assert ob["yes_price"] == 0.62
        assert ob["no_price"] == 0.39
        assert ob["yes_ask"] == 0.63
        assert ob["yes_bid"] == 0.61
        assert ob["no_ask"] == 0.40
        assert ob["no_bid"] == 0.38
        assert ob["volume_24h"] == 50000
        assert ob["data_status"] == "VALID"


class TestPriceUpdatePayload:
    def test_payload_matches_schema(self, connector):
        payload = connector._build_price_payload("0xtest", SAMPLE_MARKET_DETAIL)

        required_fields = {
            "market_id", "platform", "yes_price", "no_price",
            "yes_ask", "yes_bid", "no_ask", "no_bid",
            "volume_24h", "data_status",
        }
        assert required_fields.issubset(set(payload.keys()))
        assert isinstance(payload["yes_price"], float)
        assert isinstance(payload["no_price"], float)
        assert payload["data_status"] == "VALID"


class TestUpdatePrices:
    def test_publishes_bus_event(self, connector):
        connector.bus.publish = MagicMock()
        price_data = connector._build_price_payload("0xtest", SAMPLE_MARKET_DETAIL)

        connector.update_prices("0xtest", price_data)

        connector.bus.publish.assert_called_once()
        call_kwargs = connector.bus.publish.call_args
        assert call_kwargs[1]["topic"] == "feed:price_update" or call_kwargs[0][0] == "feed:price_update"

    def test_writes_state_file(self, connector, tmp_path):
        price_data = connector._build_price_payload("0xtest", SAMPLE_MARKET_DETAIL)
        connector.update_prices("0xtest", price_data)

        state = connector.store.read_json(PRICES_STATE_FILE)
        assert state is not None
        assert "0xtest" in state
        assert state["0xtest"]["yes_price"] == 0.62

    def test_updates_last_update_time(self, connector):
        price_data = connector._build_price_payload("0xtest", SAMPLE_MARKET_DETAIL)
        connector.update_prices("0xtest", price_data)

        assert connector._last_update_time is not None
        assert time.time() - connector._last_update_time < 2


class TestIsConnected:
    def test_false_when_no_updates(self, connector):
        assert connector.is_connected() is False

    def test_true_after_recent_update(self, connector):
        connector._last_update_time = time.time()
        assert connector.is_connected() is True

    def test_false_when_stale(self, connector):
        connector._last_update_time = time.time() - 200  # > 120s timeout
        assert connector.is_connected() is False


class TestReconnectBackoff:
    def test_initial_backoff(self, connector):
        delay = connector.calculate_reconnect_backoff()
        assert delay == 1

    def test_backoff_doubles(self, connector):
        connector.calculate_reconnect_backoff()  # 1
        delay = connector.calculate_reconnect_backoff()  # 2
        assert delay == 2
        delay = connector.calculate_reconnect_backoff()  # 4
        assert delay == 4

    def test_backoff_capped_at_max(self, connector):
        for _ in range(20):
            delay = connector.calculate_reconnect_backoff()
        assert delay <= connector.reconnect_max_backoff

    def test_backoff_resets(self, connector):
        for _ in range(5):
            connector.calculate_reconnect_backoff()
        connector.reset_reconnect_backoff()
        delay = connector.calculate_reconnect_backoff()
        assert delay == 1


class TestPlaceOrder:
    def test_requires_credentials(self, connector):
        # place_order is implemented — it raises KeyError/Exception when
        # WALLET_PRIVATE_KEY / POLYMARKET_API_KEY are absent (test environment).
        with pytest.raises(Exception):
            connector.place_order("0xabc", "YES", 100, 0.50)


class TestGetSettlement:
    @patch.object(ConnectorPolymarket, "_http_get")
    def test_resolved_market(self, mock_get, connector):
        mock_get.return_value = SAMPLE_RESOLVED_MARKET
        result = connector.get_settlement("0xresolved")

        assert result is not None
        assert result["resolved"] is True
        assert result["outcome"] == "Yes"

    @patch.object(ConnectorPolymarket, "_http_get")
    def test_unresolved_returns_none(self, mock_get, connector):
        mock_get.return_value = SAMPLE_MARKET_DETAIL  # resolved=False
        result = connector.get_settlement("0xabc123")
        assert result is None


class TestFetchAndUpdate:
    @patch.object(ConnectorPolymarket, "_http_get")
    def test_fetches_and_updates(self, mock_get, connector, tmp_path):
        mock_get.return_value = SAMPLE_MARKET_DETAIL
        connector.bus.publish = MagicMock()

        price_data = connector.fetch_and_update("0xabc123")

        assert price_data["yes_price"] == 0.62
        assert connector.is_connected() is True
        connector.bus.publish.assert_called_once()

        state = connector.store.read_json(PRICES_STATE_FILE)
        assert "0xabc123" in state
