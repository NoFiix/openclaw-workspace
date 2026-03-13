"""
connector_kalshi — Kalshi platform connector.

Implements the PolyMarketConnector interface for the Kalshi Trade API v2 (REST).
Kalshi is a CFTC-regulated US prediction market platform.

Writes to state/feeds/kalshi_prices.json and publishes feed:price_update on bus.
All HTTP calls are injectable via http_client for full test isolation.
"""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from agents.poly_market_connector import PolyMarketConnector
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus


PRODUCER = "POLY_MARKET_CONNECTOR"
PRICES_STATE_FILE = "feeds/kalshi_prices.json"

DEFAULT_BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"
DEFAULT_CONNECTION_TIMEOUT = 120  # seconds


class ConnectorKalshi(PolyMarketConnector):
    """Kalshi platform connector using Kalshi Trade API v2 (REST)."""

    def __init__(self, base_path="state", config=None, http_client=None):
        """Initialize the Kalshi connector.

        Args:
            base_path: Base path for state files.
            config: Optional config dict. Keys: base_url, connection_timeout_s.
            http_client: Injectable callable(url: str, headers: dict) -> dict.
                         If None, real urllib.request is used.
        """
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)

        cfg = config or {}
        self.base_url = cfg.get("base_url", DEFAULT_BASE_URL).rstrip("/")
        self.connection_timeout = cfg.get("connection_timeout_s", DEFAULT_CONNECTION_TIMEOUT)

        # API key from environment (never hardcode)
        self.api_key = os.environ.get("KALSHI_API_KEY", "")

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
        return "kalshi"

    def is_connected(self) -> bool:
        """True if data was received within the connection timeout."""
        if self._last_update_time is None:
            return False
        return (time.time() - self._last_update_time) < self.connection_timeout

    def get_markets(self, filter_active=True) -> list:
        """Fetch available markets from Kalshi API.

        Args:
            filter_active: If True, only return open markets.

        Returns:
            List of normalized market dicts.
        """
        url = f"{self.base_url}/markets"
        if filter_active:
            url += "?status=open"

        response = self._http_get(url)
        raw_markets = response.get("markets", [])

        markets = []
        for m in raw_markets:
            is_open = m.get("status", "") == "open"
            markets.append({
                "market_id": m.get("ticker", ""),
                "question": m.get("title", ""),
                "active": is_open,
                "end_date": m.get("expiration_time", ""),
                "platform": "kalshi",
                "volume_24h": float(m.get("volume", 0) or 0),
            })

        if filter_active:
            markets = [m for m in markets if m["active"]]

        return markets

    def get_orderbook(self, market_id: str) -> dict:
        """Fetch current prices for a market from Kalshi API.

        Args:
            market_id: Kalshi market ticker (e.g. "INXD-23DEC31-T4500").

        Returns:
            Dict matching feed:price_update payload schema.
        """
        url = f"{self.base_url}/markets/{market_id}"
        response = self._http_get(url)
        m = response.get("market", response)

        yes_bid = float(m.get("yes_bid", 0) or 0)
        yes_ask = float(m.get("yes_ask", 0) or 0)
        no_bid = float(m.get("no_bid", 0) or 0)
        no_ask = float(m.get("no_ask", 0) or 0)

        yes_price = (yes_bid + yes_ask) / 2 if (yes_bid + yes_ask) > 0 else 0.0
        no_price = (no_bid + no_ask) / 2 if (no_bid + no_ask) > 0 else 0.0

        return {
            "market_id": market_id,
            "platform": "kalshi",
            "yes_price": yes_price,
            "no_price": no_price,
            "yes_ask": yes_ask,
            "yes_bid": yes_bid,
            "no_ask": no_ask,
            "no_bid": no_bid,
            "volume_24h": float(m.get("volume", 0) or 0),
            "data_status": "VALID",
        }

    def get_settlement(self, market_id: str):
        """Fetch settlement status for a market.

        Args:
            market_id: Kalshi market ticker.

        Returns:
            Dict with resolution data, or None if not yet resolved.
        """
        url = f"{self.base_url}/markets/{market_id}"
        response = self._http_get(url)
        m = response.get("market", response)

        result = m.get("result", "")
        if not result:
            return None

        return {
            "market_id": market_id,
            "resolved": True,
            "outcome": result.upper(),  # "YES" or "NO"
            "resolved_at": m.get("close_time", ""),
        }

    def get_positions(self, wallet="") -> list:
        """Fetch current positions from Kalshi portfolio.

        Args:
            wallet: Unused for Kalshi (auth is via API key, not wallet address).

        Returns:
            List of normalized position dicts.
        """
        url = f"{self.base_url}/portfolio/positions"
        response = self._http_get(url)
        raw_positions = response.get("positions", [])

        positions = []
        for p in raw_positions:
            qty = p.get("position", 0)
            positions.append({
                "market_id": p.get("ticker", ""),
                "side": "YES" if qty > 0 else "NO",
                "size": abs(qty),
                "avg_price": float(p.get("market_exposure", 0) or 0),
            })

        return positions

    def place_order(self, market_id, side, size, price):
        """Order placement is handled by POLY_LIVE_EXECUTION_ENGINE, not the connector.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "Order placement is handled by POLY_LIVE_EXECUTION_ENGINE, "
            "not by the connector. Use the execution engine."
        )

    # ------------------------------------------------------------------
    # Data update helpers
    # ------------------------------------------------------------------

    def update_prices(self, market_id: str, price_data: dict):
        """Write prices to state file and publish bus event.

        Args:
            market_id: Market identifier (Kalshi ticker).
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
            market_id: Kalshi market ticker to fetch.

        Returns:
            The price payload dict.
        """
        price_data = self.get_orderbook(market_id)
        self.update_prices(market_id, price_data)
        return price_data

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict:
        """Build auth headers from KALSHI_API_KEY env var."""
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    def _http_get(self, url: str) -> dict:
        """Make an HTTP GET request and return parsed JSON.

        Uses injectable http_client if provided, otherwise real urllib.

        Args:
            url: Full URL to request.

        Returns:
            Parsed JSON response dict.

        Raises:
            ConnectionError: On HTTP errors or network failures.
        """
        headers = self._auth_headers()

        if self._http_client is not None:
            return self._http_client(url, headers)

        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        for key, value in headers.items():
            req.add_header(key, value)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ConnectionError(f"HTTP {e.code} from {url}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Connection failed to {url}: {e.reason}") from e
