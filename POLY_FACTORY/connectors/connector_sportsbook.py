"""
connector_sportsbook — Sportsbook platform connector.

Implements the PolyMarketConnector interface using The Odds API (theOddsAPI.com)
as an odds aggregator. Sports events are mapped to binary YES/NO markets:
  YES = home team wins
  NO  = away team wins

The key challenge: sportsbooks quote decimal odds, not 0–1 probabilities.
Vig (bookmaker's cut) inflates raw implied probabilities above 1.0.
Two module-level pure functions handle odds conversion:
  decimal_to_implied(d) → 1/d
  remove_vig(yes_impl, no_impl) → normalise to sum = 1.0

Writes to state/feeds/sportsbook_prices.json and publishes feed:price_update on bus.
All HTTP calls are injectable via http_client for full test isolation.
"""

import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

from agents.poly_market_connector import PolyMarketConnector
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus


PRODUCER = "POLY_MARKET_CONNECTOR"
PRICES_STATE_FILE = "feeds/sportsbook_prices.json"

DEFAULT_BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_SPORT = "americanfootball_nfl"
DEFAULT_CONNECTION_TIMEOUT = 120  # seconds


# ---------------------------------------------------------------------------
# Odds conversion — pure module-level functions
# ---------------------------------------------------------------------------

def decimal_to_implied(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability.

    Args:
        decimal_odds: Decimal odds (e.g. 1.91 means bet 1, win 1.91 including stake).

    Returns:
        Implied probability in [0, 1].
    """
    if decimal_odds <= 0:
        return 0.0
    return 1.0 / decimal_odds


def remove_vig(yes_implied: float, no_implied: float) -> tuple:
    """Remove bookmaker vig by normalising implied probabilities to sum to 1.0.

    Args:
        yes_implied: Raw implied probability for YES outcome (home win).
        no_implied: Raw implied probability for NO outcome (away win).

    Returns:
        Tuple (yes_fair, no_fair) that sums to 1.0.
    """
    total = yes_implied + no_implied
    if total <= 0:
        return 0.5, 0.5
    return yes_implied / total, no_implied / total


# ---------------------------------------------------------------------------
# Connector class
# ---------------------------------------------------------------------------

class ConnectorSportsbook(PolyMarketConnector):
    """Sportsbook connector using The Odds API v4 (REST)."""

    def __init__(self, base_path="state", config=None, http_client=None):
        """Initialise the sportsbook connector.

        Args:
            base_path: Base path for state files.
            config: Optional config dict. Keys: base_url, sport, connection_timeout_s.
            http_client: Injectable callable(url: str, headers: dict) -> any.
                         If None, real urllib.request is used.
        """
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)

        cfg = config or {}
        self.base_url = cfg.get("base_url", DEFAULT_BASE_URL).rstrip("/")
        self.sport = cfg.get("sport", DEFAULT_SPORT)
        self.connection_timeout = cfg.get("connection_timeout_s", DEFAULT_CONNECTION_TIMEOUT)

        # API key from environment (never hardcode)
        self.api_key = os.environ.get("ODDS_API_KEY", "")

        # Injectable HTTP client for testing
        self._http_client = http_client

        # Connection state
        self._prices_cache = {}
        self._last_update_time = None

    # ------------------------------------------------------------------
    # PolyMarketConnector interface
    # ------------------------------------------------------------------

    def get_platform(self) -> str:
        """Return platform identifier."""
        return "sportsbook"

    def is_connected(self) -> bool:
        """True if data was received within the connection timeout."""
        if self._last_update_time is None:
            return False
        return (time.time() - self._last_update_time) < self.connection_timeout

    def get_markets(self, filter_active=True) -> list:
        """Fetch upcoming sports events and normalise to the standard market format.

        Args:
            filter_active: Ignored — The Odds API only returns upcoming events.

        Returns:
            List of normalised market dicts.
        """
        url = self._build_odds_url()
        response = self._http_get(url)
        events = response if isinstance(response, list) else []

        markets = []
        for event in events:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            markets.append({
                "market_id": event.get("id", ""),
                "question": f"Will {home} beat {away}?",
                "active": True,
                "end_date": event.get("commence_time", ""),
                "platform": "sportsbook",
                "volume_24h": 0.0,
                "home_team": home,
                "away_team": away,
                "sport": event.get("sport_key", self.sport),
            })

        return markets

    def get_orderbook(self, market_id: str) -> dict:
        """Fetch and normalise odds for a specific event.

        Converts decimal odds to vig-removed implied probabilities:
          yes_price = P(home wins) after vig removal
          no_price  = P(away wins) after vig removal

        Args:
            market_id: The Odds API event ID.

        Returns:
            Dict matching feed:price_update payload schema.

        Raises:
            ValueError: If the market_id is not found in the current odds feed.
        """
        url = self._build_odds_url()
        response = self._http_get(url)
        events = response if isinstance(response, list) else []

        event = next((e for e in events if e.get("id") == market_id), None)
        if event is None:
            raise ValueError(f"Market {market_id} not found in sportsbook feed")

        home = event.get("home_team", "")
        away = event.get("away_team", "")

        # Extract h2h prices from the first available bookmaker
        yes_decimal, no_decimal = self._extract_h2h_prices(event, home, away)

        yes_raw = decimal_to_implied(yes_decimal)
        no_raw = decimal_to_implied(no_decimal)
        yes_fair, no_fair = remove_vig(yes_raw, no_raw)

        return {
            "market_id": market_id,
            "platform": "sportsbook",
            "yes_price": yes_fair,
            "no_price": no_fair,
            "yes_ask": yes_fair,
            "yes_bid": yes_fair,
            "no_ask": no_fair,
            "no_bid": no_fair,
            "volume_24h": 0.0,
            "data_status": "VALID",
            "home_team": home,
            "away_team": away,
        }

    def get_settlement(self, market_id: str):
        """Fetch settlement status for a completed event.

        Args:
            market_id: The Odds API event ID.

        Returns:
            Dict with resolution data, or None if not yet completed.
        """
        url = self._build_scores_url()
        response = self._http_get(url)
        events = response if isinstance(response, list) else []

        event = next((e for e in events if e.get("id") == market_id), None)
        if event is None or not event.get("completed", False):
            return None

        home = event.get("home_team", "")
        away = event.get("away_team", "")
        scores = {s["name"]: s["score"] for s in (event.get("scores") or [])}

        try:
            home_score = int(scores.get(home, 0))
            away_score = int(scores.get(away, 0))
        except (ValueError, TypeError):
            home_score, away_score = 0, 0

        outcome = "YES" if home_score > away_score else "NO"

        return {
            "market_id": market_id,
            "resolved": True,
            "outcome": outcome,
            "resolved_at": event.get("commence_time", ""),
        }

    def get_positions(self, wallet="") -> list:
        """Return empty list — sportsbooks don't expose portfolio positions via API."""
        return []

    def place_order(self, market_id, side, size, price):
        """Order placement not supported for sportsbooks.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Order placement is not implemented for sportsbooks. "
            "Each sportsbook requires a separate integration."
        )

    # ------------------------------------------------------------------
    # Data update helpers
    # ------------------------------------------------------------------

    def update_prices(self, market_id: str, price_data: dict):
        """Write prices to state file and publish bus event.

        Args:
            market_id: Event identifier.
            price_data: Dict matching feed:price_update payload schema.
        """
        self._prices_cache[market_id] = price_data
        self._last_update_time = time.time()

        self.store.write_json(PRICES_STATE_FILE, self._prices_cache)

        self.bus.publish(
            topic="feed:price_update",
            producer=PRODUCER,
            payload=price_data,
            priority="normal",
        )

    def fetch_and_update(self, market_id: str) -> dict:
        """Fetch orderbook via REST and update state + bus.

        Args:
            market_id: Event ID to fetch.

        Returns:
            The price payload dict.
        """
        price_data = self.get_orderbook(market_id)
        self.update_prices(market_id, price_data)
        return price_data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict:
        """The Odds API uses apiKey as a query param, not a header."""
        return {}

    def _add_api_key(self, url: str) -> str:
        """Append apiKey query parameter to a URL if api_key is set."""
        if not self.api_key:
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}apiKey={self.api_key}"

    def _build_odds_url(self) -> str:
        params = "regions=us&markets=h2h&oddsFormat=decimal"
        url = f"{self.base_url}/sports/{self.sport}/odds?{params}"
        return self._add_api_key(url)

    def _build_scores_url(self) -> str:
        params = "daysFrom=3&dateFormat=iso"
        url = f"{self.base_url}/sports/{self.sport}/scores?{params}"
        return self._add_api_key(url)

    def _extract_h2h_prices(self, event: dict, home: str, away: str) -> tuple:
        """Extract decimal odds for home and away from the first bookmaker's h2h market.

        Args:
            event: Raw event dict from The Odds API.
            home: Home team name.
            away: Away team name.

        Returns:
            Tuple (home_decimal_odds, away_decimal_odds). Defaults to 2.0 each.
        """
        bookmakers = event.get("bookmakers", [])
        for bm in bookmakers:
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                home_odds = float(outcomes.get(home, 0) or 0)
                away_odds = float(outcomes.get(away, 0) or 0)
                if home_odds > 0 and away_odds > 0:
                    return home_odds, away_odds

        # Fallback: evens (50/50)
        return 2.0, 2.0

    def _http_get(self, url: str):
        """Make an HTTP GET request and return the parsed JSON response.

        Uses injectable http_client if provided, otherwise real urllib.

        Args:
            url: Full URL (including query params).

        Returns:
            Parsed JSON (list or dict).

        Raises:
            ConnectionError: On HTTP errors or network failures.
        """
        headers = self._auth_headers()

        if self._http_client is not None:
            return self._http_client(url, headers)

        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ConnectionError(f"HTTP {e.code} from {url}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Connection failed to {url}: {e.reason}") from e
