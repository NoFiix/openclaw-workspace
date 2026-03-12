"""
POLY_WALLET_FEED — Polymarket wallet position feed.

Fetches raw positions from tracked Polymarket wallets via the Gamma API.
Polygon RPC fallback is stubbed for future implementation.
Writes to state/feeds/wallet_raw_positions.json and publishes feed:wallet_update
on the event bus. Polling every 60 seconds.
Uses only Python standard library (urllib).
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus

logger = logging.getLogger("POLY_WALLET_FEED")

STATE_FILE = "feeds/wallet_raw_positions.json"
TRACKED_WALLETS_FILE = "references/tracked_wallets.json"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
HTTP_TIMEOUT = 30
FRESHNESS_THRESHOLD = 120  # 2 minutes — matches "detection < 2 min" acceptance criterion


class PolyWalletFeed:
    """Polymarket wallet position feed for tracked wallets."""

    def __init__(self, base_path="state", wallets_config_path=None, config=None):
        """Initialize the wallet feed.

        Args:
            base_path: Base path for state files.
            wallets_config_path: Path to tracked_wallets.json. Defaults to
                references/tracked_wallets.json relative to project root.
            config: Optional config dict with gamma_api_base, polygon_rpc_url.
        """
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)

        if wallets_config_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            wallets_config_path = os.path.join(project_root, TRACKED_WALLETS_FILE)

        with open(wallets_config_path, "r", encoding="utf-8") as f:
            self.wallets = json.load(f)

        config = config or {}
        self.gamma_api_base = config.get("gamma_api_base", GAMMA_API_BASE)
        self.polygon_rpc_url = config.get(
            "polygon_rpc_url", os.environ.get("POLYGON_RPC_URL", "")
        )

        self._state_cache = {}
        self._last_update_times = {}

    def _http_get(self, url):
        """Make an HTTP GET request and return parsed JSON.

        Args:
            url: Full URL to fetch.

        Returns:
            Parsed JSON (dict or list).

        Raises:
            ConnectionError: On HTTP errors or network failures.
            TimeoutError: On request timeout.
        """
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            raise ConnectionError(f"HTTP {e.code} from {url}: {e.reason}") from e
        except urllib.error.URLError as e:
            if "timed out" in str(e.reason):
                raise TimeoutError(f"Timeout fetching {url}") from e
            raise ConnectionError(f"Connection failed to {url}: {e.reason}") from e
        except Exception as e:
            if "timed out" in str(e):
                raise TimeoutError(f"Timeout fetching {url}") from e
            raise

    def fetch_positions_gamma(self, wallet):
        """Fetch positions for a wallet via the Polymarket Gamma API.

        Args:
            wallet: Ethereum wallet address.

        Returns:
            List of position dicts: [{market_id, side, size, avg_price}].
        """
        url = f"{self.gamma_api_base}/positions?user={wallet}"
        data = self._http_get(url)

        # Handle both list and {"data": [...]} response shapes
        if isinstance(data, dict):
            positions_raw = data.get("data", data.get("positions", []))
        elif isinstance(data, list):
            positions_raw = data
        else:
            positions_raw = []

        positions = []
        for pos in positions_raw:
            positions.append({
                "market_id": pos.get("conditionId", pos.get("market", pos.get("asset", ""))),
                "side": pos.get("outcome", "YES").upper(),
                "size": float(pos.get("size", 0) or 0),
                "avg_price": float(pos.get("avgPrice", pos.get("avg_price", 0)) or 0),
            })

        return positions

    def fetch_positions_rpc(self, wallet):
        """Fetch positions via Polygon RPC (stub for future implementation).

        Args:
            wallet: Ethereum wallet address.

        Returns:
            List of position dicts (currently empty).

        Raises:
            ConnectionError: If POLYGON_RPC_URL is not configured.
        """
        if not self.polygon_rpc_url:
            raise ConnectionError("POLYGON_RPC_URL not configured")

        logger.warning(
            "Polygon RPC position fetch not yet implemented for %s", wallet
        )
        return []

    def fetch_wallet(self, wallet):
        """Fetch positions for a wallet with Gamma primary, RPC fallback.

        Args:
            wallet: Ethereum wallet address.

        Returns:
            Payload dict for feed:wallet_update.
        """
        try:
            positions = self.fetch_positions_gamma(wallet)
        except (ConnectionError, TimeoutError) as e:
            logger.warning("Gamma API failed for %s: %s — trying RPC", wallet, e)
            positions = self.fetch_positions_rpc(wallet)

        return self._build_payload(wallet, positions)

    def _build_payload(self, wallet, positions, data_status="VALID"):
        """Build a feed:wallet_update payload.

        Args:
            wallet: Ethereum wallet address.
            positions: List of position dicts [{market_id, side, size, avg_price}].
            data_status: "VALID" or "STALE".

        Returns:
            Dict matching feed:wallet_update schema.
        """
        return {
            "wallet": wallet,
            "positions": positions,
            "data_status": data_status,
        }

    def update(self, wallet, payload):
        """Write payload to state file and publish bus event.

        Args:
            wallet: Wallet address (key for state cache).
            payload: Dict matching feed:wallet_update schema.
        """
        self._state_cache[wallet] = payload
        self._last_update_times[wallet] = time.time()

        self.store.write_json(STATE_FILE, self._state_cache)

        self.bus.publish(
            topic="feed:wallet_update",
            producer="POLY_WALLET_FEED",
            payload=payload,
            priority="normal",
        )

    def poll_once(self):
        """Fetch all tracked wallets and update state + bus.

        Returns:
            Dict of {wallet: payload} for all wallets.
            Failed wallets get data_status "STALE" in results but are NOT
            written to state/bus (preserves last good data).
        """
        results = {}
        for wallet, info in self.wallets.items():
            try:
                payload = self.fetch_wallet(wallet)
                self.update(wallet, payload)
                results[wallet] = payload
            except (ConnectionError, TimeoutError, ValueError, KeyError) as e:
                logger.error("Failed to fetch %s (%s): %s", wallet, info.get("label", ""), e)
                stale_payload = self._build_payload(wallet, [], data_status="STALE")
                results[wallet] = stale_payload
        return results

    def is_connected(self):
        """Check if at least 1 wallet was updated within the freshness threshold."""
        if not self._last_update_times:
            return False
        now = time.time()
        return any(
            (now - t) < FRESHNESS_THRESHOLD
            for t in self._last_update_times.values()
        )
