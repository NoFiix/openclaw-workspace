"""
POLY_BINANCE_FEED — Binance data feed for BTC/ETH prices + orderbook.

Connects to Binance via REST (fallback) or WebSocket (streaming) to provide
real-time price and orderbook data. Writes to state/feeds/binance_raw.json
and publishes feed:binance_update on the event bus.
Uses only Python standard library for REST. WebSocket streaming is optional.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus

logger = logging.getLogger("POLY_BINANCE_FEED")

# State file
STATE_FILE = "feeds/binance_raw.json"

# Default symbols to track
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]

# Binance API endpoints
BINANCE_REST_BASE = "https://api.binance.com"
BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"

# Connection settings
DEFAULT_CONNECTION_TIMEOUT = 120
DEFAULT_RECONNECT_INITIAL = 1
DEFAULT_RECONNECT_MAX_BACKOFF = 30


class PolyBinanceFeed:
    """Binance data feed for BTC/ETH prices and orderbook depth."""

    def __init__(self, base_path="state", symbols=None, config=None):
        """Initialize the Binance feed.

        Args:
            base_path: Base path for state files.
            symbols: List of symbols to track. Defaults to BTCUSDT, ETHUSDT.
            config: Optional config dict for connection settings.
        """
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)

        self.symbols = symbols or list(DEFAULT_SYMBOLS)

        config = config or {}
        self.rest_base = config.get("rest_base_url", BINANCE_REST_BASE)
        self.ws_base = config.get("ws_base_url", BINANCE_WS_BASE)
        self.connection_timeout = config.get("connection_timeout_s", DEFAULT_CONNECTION_TIMEOUT)
        self.reconnect_initial = config.get("reconnect_initial_s", DEFAULT_RECONNECT_INITIAL)
        self.reconnect_max_backoff = config.get("reconnect_max_backoff_s", DEFAULT_RECONNECT_MAX_BACKOFF)

        # API key from environment (read-only, optional for public endpoints)
        self.api_key = os.environ.get("BINANCE_API_KEY", "")

        # Connection state
        self._last_update_time = None
        self._reconnect_backoff = self.reconnect_initial
        self._state_cache = {}  # symbol -> latest payload

    def _http_get(self, url):
        """Make an HTTP GET request and return parsed JSON.

        Raises:
            ConnectionError: On HTTP errors or network failures.
        """
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")

        if self.api_key:
            req.add_header("X-MBX-APIKEY", self.api_key)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            raise ConnectionError(f"HTTP {e.code} from {url}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Connection failed to {url}: {e.reason}") from e

    def fetch_price(self, symbol):
        """Fetch current price for a symbol via REST.

        Args:
            symbol: Trading pair (e.g. "BTCUSDT").

        Returns:
            Dict with {symbol, price}.
        """
        url = f"{self.rest_base}/api/v3/ticker/price?symbol={symbol}"
        data = self._http_get(url)
        return {
            "symbol": data.get("symbol", symbol),
            "price": float(data.get("price", 0)),
        }

    def fetch_orderbook(self, symbol, limit=5):
        """Fetch orderbook depth for a symbol via REST.

        Args:
            symbol: Trading pair.
            limit: Number of levels (default 5).

        Returns:
            Dict with {bids, asks} as lists of [price, qty] pairs.
        """
        url = f"{self.rest_base}/api/v3/depth?symbol={symbol}&limit={limit}"
        data = self._http_get(url)

        bids = [[float(b[0]), float(b[1])] for b in data.get("bids", [])]
        asks = [[float(a[0]), float(a[1])] for a in data.get("asks", [])]

        return {"bids": bids, "asks": asks}

    def fetch_snapshot(self, symbol):
        """Fetch a complete snapshot (price + orderbook) for a symbol.

        Args:
            symbol: Trading pair.

        Returns:
            Full payload dict matching feed:binance_update schema.
        """
        price_data = self.fetch_price(symbol)
        ob_data = self.fetch_orderbook(symbol, limit=5)

        return self._build_payload(
            symbol=symbol,
            price=price_data["price"],
            bids=ob_data["bids"],
            asks=ob_data["asks"],
            last_trade_qty=0.0,
        )

    def _build_payload(self, symbol, price, bids, asks, last_trade_qty):
        """Build a feed:binance_update payload.

        Args:
            symbol: Trading pair.
            price: Last trade price.
            bids: Top bid levels [[price, qty], ...].
            asks: Top ask levels [[price, qty], ...].
            last_trade_qty: Quantity of last trade.

        Returns:
            Dict matching feed:binance_update schema.
        """
        return {
            "symbol": symbol,
            "price": float(price),
            "bids_top5": bids[:5],
            "asks_top5": asks[:5],
            "last_trade_qty": float(last_trade_qty),
            "data_status": "VALID",
        }

    def update(self, symbol, payload):
        """Write payload to state file and publish bus event.

        Args:
            symbol: Trading pair key for state cache.
            payload: Dict matching feed:binance_update schema.
        """
        self._state_cache[symbol] = payload
        self._last_update_time = time.time()

        # Write full cache to state file
        self.store.write_json(STATE_FILE, self._state_cache)

        # Publish bus event
        self.bus.publish(
            topic="feed:binance_update",
            producer="POLY_BINANCE_FEED",
            payload=payload,
            priority="normal",
        )

    def poll_once(self):
        """Fetch all symbols via REST and update state + bus.

        Returns:
            Dict of {symbol: payload} for all successfully fetched symbols.
        """
        results = {}
        for symbol in self.symbols:
            try:
                payload = self.fetch_snapshot(symbol)
                self.update(symbol, payload)
                results[symbol] = payload
            except ConnectionError as e:
                logger.error("Failed to fetch %s: %s", symbol, e)
        return results

    def parse_agg_trade(self, msg):
        """Parse a Binance aggTrade WebSocket message.

        Args:
            msg: Parsed JSON message from aggTrade stream.

        Returns:
            Dict with {symbol, price, last_trade_qty}.
        """
        return {
            "symbol": msg.get("s", ""),
            "price": float(msg.get("p", 0)),
            "last_trade_qty": float(msg.get("q", 0)),
        }

    def parse_depth(self, msg):
        """Parse a Binance depth20 WebSocket message.

        Args:
            msg: Parsed JSON message from depth stream.

        Returns:
            Dict with {bids, asks} as lists of [price, qty].
        """
        bids = [[float(b[0]), float(b[1])] for b in msg.get("bids", msg.get("b", []))]
        asks = [[float(a[0]), float(a[1])] for a in msg.get("asks", msg.get("a", []))]
        return {"bids": bids[:5], "asks": asks[:5]}

    def is_connected(self):
        """Check if the feed is healthy (received data within timeout)."""
        if self._last_update_time is None:
            return False
        elapsed = time.time() - self._last_update_time
        return elapsed < self.connection_timeout

    def calculate_reconnect_backoff(self):
        """Calculate next reconnect delay with exponential backoff.

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

    def get_ws_stream_url(self):
        """Build the combined WebSocket stream URL for all symbols.

        Returns:
            Full WebSocket URL for combined streams.
        """
        streams = []
        for symbol in self.symbols:
            s = symbol.lower()
            streams.append(f"{s}@aggTrade")
            streams.append(f"{s}@depth20@100ms")

        return f"{self.ws_base}/{'/'.join(streams)}"
