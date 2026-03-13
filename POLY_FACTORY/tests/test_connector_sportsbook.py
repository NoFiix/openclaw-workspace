"""
Tests for connector_sportsbook — 12 tests covering the full PolyMarketConnector
interface, odds conversion, and injectable HTTP client (no real network calls).
"""

import pytest

from connectors.connector_sportsbook import (
    ConnectorSportsbook,
    decimal_to_implied,
    remove_vig,
)


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

_ODDS_RESPONSE = [
    {
        "id": "abc123",
        "sport_key": "americanfootball_nfl",
        "sport_title": "NFL",
        "commence_time": "2023-11-05T18:00:00Z",
        "home_team": "Tampa Bay Buccaneers",
        "away_team": "Dallas Cowboys",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Tampa Bay Buccaneers", "price": 1.91},
                            {"name": "Dallas Cowboys", "price": 2.05},
                        ],
                    }
                ],
            }
        ],
    }
]

_SCORES_RESPONSE = [
    {
        "id": "abc123",
        "sport_key": "americanfootball_nfl",
        "commence_time": "2023-11-05T18:00:00Z",
        "completed": True,
        "home_team": "Tampa Bay Buccaneers",
        "away_team": "Dallas Cowboys",
        "scores": [
            {"name": "Tampa Bay Buccaneers", "score": "24"},
            {"name": "Dallas Cowboys", "score": "14"},
        ],
    }
]

_SCORES_AWAY_WINS = [
    {
        "id": "abc123",
        "sport_key": "americanfootball_nfl",
        "commence_time": "2023-11-05T18:00:00Z",
        "completed": True,
        "home_team": "Tampa Bay Buccaneers",
        "away_team": "Dallas Cowboys",
        "scores": [
            {"name": "Tampa Bay Buccaneers", "score": "10"},
            {"name": "Dallas Cowboys", "score": "28"},
        ],
    }
]


# ---------------------------------------------------------------------------
# Mock HTTP client
# ---------------------------------------------------------------------------

def _mock_http(odds=None, scores=None):
    """Return an http_client callable that routes by URL substring."""
    def client(url, headers):
        if "/scores" in url and scores is not None:
            return scores
        if "/odds" in url and odds is not None:
            return odds
        raise ConnectionError(f"No mock for {url}")
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    """Connector with empty mock (no HTTP calls made)."""
    return ConnectorSportsbook(
        base_path=str(tmp_path),
        http_client=_mock_http(odds=_ODDS_RESPONSE, scores=_SCORES_RESPONSE),
    )


@pytest.fixture
def conn_no_http(tmp_path):
    """Connector that should not need HTTP (for non-fetch tests)."""
    return ConnectorSportsbook(
        base_path=str(tmp_path),
        http_client=_mock_http(odds=[], scores=[]),
    )


# ---------------------------------------------------------------------------
# Platform identity
# ---------------------------------------------------------------------------

def test_get_platform_returns_sportsbook(conn_no_http):
    assert conn_no_http.get_platform() == "sportsbook"


# ---------------------------------------------------------------------------
# Connection status
# ---------------------------------------------------------------------------

def test_is_connected_false_on_init(conn_no_http):
    assert conn_no_http.is_connected() is False


def test_is_connected_true_after_update(conn_no_http):
    price_data = {
        "market_id": "abc123", "platform": "sportsbook",
        "yes_price": 0.52, "no_price": 0.48,
        "yes_ask": 0.52, "yes_bid": 0.52,
        "no_ask": 0.48, "no_bid": 0.48,
        "volume_24h": 0.0, "data_status": "VALID",
        "home_team": "TB", "away_team": "DAL",
    }
    conn_no_http.update_prices("abc123", price_data)
    assert conn_no_http.is_connected() is True


# ---------------------------------------------------------------------------
# Odds conversion (pure functions)
# ---------------------------------------------------------------------------

def test_decimal_to_implied_correct():
    assert decimal_to_implied(2.0) == pytest.approx(0.5)
    assert decimal_to_implied(1.91) == pytest.approx(1 / 1.91)
    assert decimal_to_implied(0) == 0.0


def test_remove_vig_sums_to_one():
    # 1/1.91 + 1/2.05 ≈ 1.04 → after vig removal should sum to 1.0
    yes_raw = decimal_to_implied(1.91)
    no_raw = decimal_to_implied(2.05)
    yes_fair, no_fair = remove_vig(yes_raw, no_raw)
    assert yes_fair + no_fair == pytest.approx(1.0, abs=1e-9)
    assert 0 < yes_fair < 1
    assert 0 < no_fair < 1


# ---------------------------------------------------------------------------
# get_markets
# ---------------------------------------------------------------------------

def test_get_markets_returns_normalized_list(conn):
    markets = conn.get_markets()
    assert len(markets) == 1
    m = markets[0]
    assert m["market_id"] == "abc123"
    assert m["platform"] == "sportsbook"
    assert m["active"] is True


def test_get_markets_question_contains_team_names(conn):
    markets = conn.get_markets()
    question = markets[0]["question"]
    assert "Tampa Bay Buccaneers" in question
    assert "Dallas Cowboys" in question


# ---------------------------------------------------------------------------
# get_orderbook
# ---------------------------------------------------------------------------

def test_get_orderbook_prices_sum_to_one(conn):
    payload = conn.get_orderbook("abc123")
    assert payload["yes_price"] + payload["no_price"] == pytest.approx(1.0, abs=1e-9)


def test_get_orderbook_platform_is_sportsbook(conn):
    payload = conn.get_orderbook("abc123")
    assert payload["platform"] == "sportsbook"
    assert payload["market_id"] == "abc123"
    assert "home_team" in payload
    assert "away_team" in payload
    assert payload["data_status"] == "VALID"


# ---------------------------------------------------------------------------
# get_settlement
# ---------------------------------------------------------------------------

def test_get_settlement_home_wins_returns_yes(conn):
    result = conn.get_settlement("abc123")
    assert result is not None
    assert result["resolved"] is True
    assert result["outcome"] == "YES"   # Tampa Bay won 24-14
    assert result["market_id"] == "abc123"


def test_get_settlement_away_wins_returns_no(tmp_path):
    conn = ConnectorSportsbook(
        base_path=str(tmp_path),
        http_client=_mock_http(scores=_SCORES_AWAY_WINS),
    )
    result = conn.get_settlement("abc123")
    assert result is not None
    assert result["outcome"] == "NO"   # Dallas won 28-10


# ---------------------------------------------------------------------------
# place_order
# ---------------------------------------------------------------------------

def test_place_order_raises_not_implemented(conn_no_http):
    with pytest.raises(NotImplementedError):
        conn_no_http.place_order("abc123", "YES", 10, 0.52)


# ---------------------------------------------------------------------------
# update_prices
# ---------------------------------------------------------------------------

def test_update_prices_publishes_bus_event(conn_no_http):
    price_data = {
        "market_id": "abc123", "platform": "sportsbook",
        "yes_price": 0.52, "no_price": 0.48,
        "yes_ask": 0.52, "yes_bid": 0.52,
        "no_ask": 0.48, "no_bid": 0.48,
        "volume_24h": 0.0, "data_status": "VALID",
        "home_team": "Tampa Bay Buccaneers",
        "away_team": "Dallas Cowboys",
    }
    conn_no_http.update_prices("abc123", price_data)
    events = conn_no_http.bus.poll("test_consumer", topics=["feed:price_update"])
    assert len(events) == 1
    assert events[0]["payload"]["platform"] == "sportsbook"
    assert events[0]["payload"]["market_id"] == "abc123"
