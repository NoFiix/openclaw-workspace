"""
Tests for connector_kalshi — 12 tests covering the full PolyMarketConnector
interface with injectable HTTP client (no real network calls).
"""

import pytest

from connectors.connector_kalshi import ConnectorKalshi


# ---------------------------------------------------------------------------
# Mock HTTP client helpers
# ---------------------------------------------------------------------------

def _mock_http(responses: dict):
    """Return a callable that maps URL substring → response dict."""
    def client(url, headers):
        for key, val in responses.items():
            if key in url:
                return val
        raise ConnectionError(f"No mock for {url}")
    return client


_MARKETS_RESPONSE = {
    "markets": [
        {
            "ticker": "INXD-23DEC31-T4500",
            "title": "Will S&P 500 close above 4,500?",
            "status": "open",
            "yes_bid": 0.44, "yes_ask": 0.46,
            "no_bid": 0.54,  "no_ask": 0.56,
            "volume": 125000,
            "expiration_time": "2023-12-31T21:00:00Z",
        },
        {
            "ticker": "TRUMP-WIN-2024",
            "title": "Will Trump win the 2024 election?",
            "status": "settled",
            "yes_bid": 0.0, "yes_ask": 0.0,
            "no_bid": 0.0,  "no_ask": 0.0,
            "volume": 500000,
            "expiration_time": "2024-11-05T21:00:00Z",
        },
    ]
}

_SINGLE_MARKET_RESPONSE = {
    "market": {
        "ticker": "INXD-23DEC31-T4500",
        "title": "Will S&P 500 close above 4,500?",
        "status": "open",
        "result": "",
        "yes_bid": 0.44, "yes_ask": 0.46,
        "no_bid": 0.54,  "no_ask": 0.56,
        "volume": 125000,
        "expiration_time": "2023-12-31T21:00:00Z",
        "close_time": "",
    }
}

_RESOLVED_MARKET_RESPONSE = {
    "market": {
        "ticker": "TRUMP-WIN-2024",
        "title": "Will Trump win the 2024 election?",
        "status": "settled",
        "result": "yes",
        "yes_bid": 1.0, "yes_ask": 1.0,
        "no_bid": 0.0,  "no_ask": 0.0,
        "volume": 500000,
        "expiration_time": "2024-11-05T21:00:00Z",
        "close_time": "2024-11-06T02:00:00Z",
    }
}

_POSITIONS_RESPONSE = {
    "positions": [
        {"ticker": "INXD-23DEC31-T4500", "position": 10, "market_exposure": 4.5, "realized_pnl": 0.0},
        {"ticker": "TRUMP-WIN-2024", "position": -5, "market_exposure": 2.5, "realized_pnl": 1.0},
    ]
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    """Connector with empty mock (tests that don't call HTTP)."""
    return ConnectorKalshi(base_path=str(tmp_path), http_client=_mock_http({}))


@pytest.fixture
def conn_markets(tmp_path):
    return ConnectorKalshi(
        base_path=str(tmp_path),
        http_client=_mock_http({"/markets": _MARKETS_RESPONSE}),
    )


@pytest.fixture
def conn_single(tmp_path):
    return ConnectorKalshi(
        base_path=str(tmp_path),
        http_client=_mock_http({
            "/markets/INXD-23DEC31-T4500": _SINGLE_MARKET_RESPONSE,
            "/markets/TRUMP-WIN-2024": _RESOLVED_MARKET_RESPONSE,
        }),
    )


@pytest.fixture
def conn_positions(tmp_path):
    return ConnectorKalshi(
        base_path=str(tmp_path),
        http_client=_mock_http({"/portfolio/positions": _POSITIONS_RESPONSE}),
    )


# ---------------------------------------------------------------------------
# Platform identity
# ---------------------------------------------------------------------------

def test_get_platform_returns_kalshi(conn):
    assert conn.get_platform() == "kalshi"


# ---------------------------------------------------------------------------
# Connection status
# ---------------------------------------------------------------------------

def test_is_connected_false_on_init(conn):
    assert conn.is_connected() is False


def test_is_connected_true_after_update(conn):
    price_data = {
        "market_id": "TEST", "platform": "kalshi",
        "yes_price": 0.5, "no_price": 0.5,
        "yes_ask": 0.51, "yes_bid": 0.49,
        "no_ask": 0.51, "no_bid": 0.49,
        "volume_24h": 1000, "data_status": "VALID",
    }
    conn.update_prices("TEST", price_data)
    assert conn.is_connected() is True


# ---------------------------------------------------------------------------
# get_markets
# ---------------------------------------------------------------------------

def test_get_markets_returns_normalized_list(conn_markets):
    # filter_active=False returns all markets
    markets = conn_markets.get_markets(filter_active=False)
    assert len(markets) == 2
    tickers = {m["market_id"] for m in markets}
    assert "INXD-23DEC31-T4500" in tickers
    assert "TRUMP-WIN-2024" in tickers
    assert all(m["platform"] == "kalshi" for m in markets)


def test_get_markets_filter_active_excludes_closed(conn_markets):
    markets = conn_markets.get_markets(filter_active=True)
    assert len(markets) == 1
    assert markets[0]["market_id"] == "INXD-23DEC31-T4500"
    assert markets[0]["active"] is True


# ---------------------------------------------------------------------------
# get_orderbook
# ---------------------------------------------------------------------------

def test_get_orderbook_returns_all_price_fields(conn_single):
    payload = conn_single.get_orderbook("INXD-23DEC31-T4500")
    for field in ("yes_price", "no_price", "yes_ask", "yes_bid", "no_ask", "no_bid", "volume_24h"):
        assert field in payload, f"Missing field: {field}"
    assert payload["data_status"] == "VALID"


def test_get_orderbook_platform_is_kalshi(conn_single):
    payload = conn_single.get_orderbook("INXD-23DEC31-T4500")
    assert payload["platform"] == "kalshi"
    assert payload["market_id"] == "INXD-23DEC31-T4500"


# ---------------------------------------------------------------------------
# get_settlement
# ---------------------------------------------------------------------------

def test_get_settlement_resolved_returns_outcome(conn_single):
    result = conn_single.get_settlement("TRUMP-WIN-2024")
    assert result is not None
    assert result["resolved"] is True
    assert result["outcome"] == "YES"
    assert result["market_id"] == "TRUMP-WIN-2024"


def test_get_settlement_unresolved_returns_none(conn_single):
    result = conn_single.get_settlement("INXD-23DEC31-T4500")
    assert result is None


# ---------------------------------------------------------------------------
# place_order
# ---------------------------------------------------------------------------

def test_place_order_raises_not_implemented(conn):
    with pytest.raises(NotImplementedError):
        conn.place_order("INXD-23DEC31-T4500", "YES", 10, 0.45)


# ---------------------------------------------------------------------------
# update_prices
# ---------------------------------------------------------------------------

def test_update_prices_writes_state_file(conn):
    price_data = {
        "market_id": "INXD-23DEC31-T4500", "platform": "kalshi",
        "yes_price": 0.45, "no_price": 0.55,
        "yes_ask": 0.46, "yes_bid": 0.44,
        "no_ask": 0.56, "no_bid": 0.54,
        "volume_24h": 125000, "data_status": "VALID",
    }
    conn.update_prices("INXD-23DEC31-T4500", price_data)
    stored = conn.store.read_json("feeds/kalshi_prices.json")
    assert "INXD-23DEC31-T4500" in stored
    assert stored["INXD-23DEC31-T4500"]["platform"] == "kalshi"


def test_update_prices_publishes_bus_event(conn):
    price_data = {
        "market_id": "INXD-23DEC31-T4500", "platform": "kalshi",
        "yes_price": 0.45, "no_price": 0.55,
        "yes_ask": 0.46, "yes_bid": 0.44,
        "no_ask": 0.56, "no_bid": 0.54,
        "volume_24h": 125000, "data_status": "VALID",
    }
    conn.update_prices("INXD-23DEC31-T4500", price_data)
    events = conn.bus.poll("test_consumer", topics=["feed:price_update"])
    assert len(events) == 1
    assert events[0]["payload"]["platform"] == "kalshi"
    assert events[0]["payload"]["market_id"] == "INXD-23DEC31-T4500"
