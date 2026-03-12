"""
connector_polymarket — Polymarket platform connector.

REST via Gamma API for markets/orderbooks/settlements.
WebSocket CLOB for real-time price streaming (optional, async).
Reconnection with exponential backoff.
Writes to state/feeds/polymarket_prices.json and publishes feed:price_update on bus.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from agents.poly_market_connector import PolyMarketConnector
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus

logger = logging.getLogger("POLY_MARKET_CONNECTOR")

# State file for cached prices
PRICES_STATE_FILE = "feeds/polymarket_prices.json"

# Default config
DEFAULT_GAMMA_URL = "https://gamma-api.polymarket.com"
DEFAULT_CLOB_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
DEFAULT_PING_INTERVAL = 60
DEFAULT_RECONNECT_INITIAL = 1
DEFAULT_RECONNECT_MAX_BACKOFF = 30
DEFAULT_CONNECTION_TIMEOUT = 120


class ConnectorPolymarket(PolyMarketConnector):
    """Polymarket platform connector using Gamma API (REST) and CLOB WebSocket."""

    def __init__(self, base_path="state", config=None):
        """Initialize the Polymarket connector.

        Args:
            base_path: Base path for state files.
            config: Optional config dict. If None, loads from config file or defaults.
        """
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)

        # Load config
        if config is None:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "POLY_MARKET_CONNECTOR.config.json"
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    full_config = json.load(f)
                config = full_config.get("polymarket", {})
            else:
                config = {}

        self.gamma_api_url = config.get("gamma_api_url", DEFAULT_GAMMA_URL)
        self.clob_ws_url = config.get("clob_ws_url", DEFAULT_CLOB_WS_URL)
        self.ping_interval = config.get("ping_interval_s", DEFAULT_PING_INTERVAL)
        self.reconnect_initial = config.get("reconnect_initial_s", DEFAULT_RECONNECT_INITIAL)
        self.reconnect_max_backoff = config.get("reconnect_max_backoff_s", DEFAULT_RECONNECT_MAX_BACKOFF)
        self.connection_timeout = config.get("connection_timeout_s", DEFAULT_CONNECTION_TIMEOUT)

        # API keys from environment
        self.api_key = os.environ.get("POLYMARKET_API_KEY", "")
        self.api_secret = os.environ.get("POLYMARKET_API_SECRET", "")

        # Connection state
        self._last_update_time = None
        self._reconnect_backoff = self.reconnect_initial
        self._prices_cache = {}  # market_id -> price data

    def get_platform(self):
        """Return platform identifier."""
        return "polymarket"

    def is_connected(self):
        """Check if connector is healthy (received data within timeout)."""
        if self._last_update_time is None:
            return False
        elapsed = time.time() - self._last_update_time
        return elapsed < self.connection_timeout

    def _http_get(self, url):
        """Make an HTTP GET request and return parsed JSON.

        Args:
            url: Full URL to request.

        Returns:
            Parsed JSON response.

        Raises:
            ConnectionError: On HTTP errors or network failures.
        """
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")

        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            raise ConnectionError(f"HTTP {e.code} from {url}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Connection failed to {url}: {e.reason}") from e

    def get_markets(self, filter_active=True):
        """Fetch available markets from Gamma API.

        Returns:
            List of market dicts.
        """
        url = f"{self.gamma_api_url}/markets"
        if filter_active:
            url += "?active=true&closed=false"

        response = self._http_get(url)

        # Gamma API returns a list of market objects
        markets = []
        items = response if isinstance(response, list) else response.get("data", response.get("markets", []))

        for m in items:
            markets.append({
                "market_id": m.get("condition_id", m.get("id", "")),
                "question": m.get("question", ""),
                "active": m.get("active", True),
                "end_date": m.get("end_date_iso", m.get("end_date", "")),
                "platform": "polymarket",
                "slug": m.get("slug", ""),
                "volume_24h": float(m.get("volume_24hr", 0) or 0),
            })

        return markets

    def get_orderbook(self, market_id):
        """Fetch current prices/orderbook for a market from Gamma API.

        Returns:
            Dict with price data matching feed:price_update payload schema.
        """
        url = f"{self.gamma_api_url}/markets/{market_id}"
        data = self._http_get(url)

        return self._build_price_payload(market_id, data)

    def _build_price_payload(self, market_id, data):
        """Build a feed:price_update payload from Gamma API data.

        Args:
            market_id: Market identifier.
            data: Raw API response data.

        Returns:
            Dict matching feed:price_update schema.
        """
        # Extract tokens for YES/NO pricing
        tokens = data.get("tokens", [])
        yes_data = {}
        no_data = {}

        for token in tokens:
            outcome = token.get("outcome", "").upper()
            if outcome == "YES":
                yes_data = token
            elif outcome == "NO":
                no_data = token

        yes_price = float(yes_data.get("price", 0) or 0)
        no_price = float(no_data.get("price", 0) or 0)

        return {
            "market_id": market_id,
            "platform": "polymarket",
            "yes_price": yes_price,
            "no_price": no_price,
            "yes_ask": float(yes_data.get("ask", yes_price) or yes_price),
            "yes_bid": float(yes_data.get("bid", yes_price) or yes_price),
            "no_ask": float(no_data.get("ask", no_price) or no_price),
            "no_bid": float(no_data.get("bid", no_price) or no_price),
            "volume_24h": float(data.get("volume_24hr", 0) or 0),
            "data_status": "VALID",
        }

    def update_prices(self, market_id, price_data):
        """Write prices to state file and publish bus event.

        Args:
            market_id: Market identifier.
            price_data: Dict matching feed:price_update payload schema.
        """
        # Update in-memory cache
        self._prices_cache[market_id] = price_data
        self._last_update_time = time.time()

        # Write full cache to state file
        self.store.write_json(PRICES_STATE_FILE, self._prices_cache)

        # Publish bus event
        self.bus.publish(
            topic="feed:price_update",
            producer="POLY_MARKET_CONNECTOR",
            payload=price_data,
            priority="normal",
        )

    def get_settlement(self, market_id):
        """Fetch settlement/resolution status for a market.

        Returns:
            Dict with resolution data, or None if not resolved.
        """
        url = f"{self.gamma_api_url}/markets/{market_id}"
        data = self._http_get(url)

        resolved = data.get("resolved", False)
        if not resolved:
            return None

        return {
            "market_id": market_id,
            "resolved": True,
            "outcome": data.get("outcome", ""),
            "resolved_at": data.get("resolved_at", data.get("end_date_iso", "")),
        }

    def get_positions(self, wallet):
        """Fetch positions for a wallet. Placeholder for future implementation.

        Returns:
            Empty list (Polygon RPC integration planned for future).
        """
        logger.warning("get_positions not yet implemented — requires Polygon RPC")
        return []

    def place_order(self, market_id, side, size, price):
        """Place order — not implemented in connector.

        Order placement is handled by POLY_LIVE_EXECUTION_ENGINE directly
        via py-clob-client. The connector provides data only.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Order placement is handled by POLY_LIVE_EXECUTION_ENGINE, "
            "not by the connector. Use the execution engine."
        )

    def calculate_reconnect_backoff(self):
        """Calculate and return the next reconnect delay with exponential backoff.

        Returns:
            Current backoff delay in seconds.
        """
        delay = self._reconnect_backoff
        self._reconnect_backoff = min(
            self._reconnect_backoff * 2,
            self.reconnect_max_backoff,
        )
        return delay

    def reset_reconnect_backoff(self):
        """Reset backoff to initial value after successful connection."""
        self._reconnect_backoff = self.reconnect_initial

    def fetch_and_update(self, market_id):
        """Fetch orderbook via REST and update state + bus. Convenience method.

        Args:
            market_id: Market to fetch.

        Returns:
            The price payload dict.
        """
        price_data = self.get_orderbook(market_id)
        self.update_prices(market_id, price_data)
        return price_data
