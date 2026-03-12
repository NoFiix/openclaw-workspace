"""
POLY_MARKET_STRUCTURE_ANALYZER — Microstructure metrics per Polymarket market.

Consumes `feed:price_update` events and computes:
  - spread_bps, depth_usd, slippage_1k, liquidity_score, executability_score (0-100)

Publishes `signal:market_structure` on every update.
Publishes `market:illiquid` when executability_score < ILLIQUID_THRESHOLD.
State written to state/feeds/market_structure.json.

Mandatory pre-trade filter: executability_score >= 40 (guard chain layer 1).
Pure deterministic logic, no external APIs.
"""

import math
import logging

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus

logger = logging.getLogger("POLY_MARKET_STRUCTURE_ANALYZER")

STATE_FILE = "feeds/market_structure.json"
ILLIQUID_THRESHOLD = 40


class PolyMarketStructureAnalyzer:
    """Computes microstructure metrics from Polymarket price feed events."""

    def __init__(self, base_path="state"):
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self._state_cache = {}

    # ------------------------------------------------------------------
    # Pure computation methods
    # ------------------------------------------------------------------

    def _compute_spread_bps(self, yes_bid, yes_ask):
        """Compute YES-side spread in basis points.

        Args:
            yes_bid: Best bid price for YES token.
            yes_ask: Best ask price for YES token.

        Returns:
            Float >= 0. 0.0 when bid == ask or inputs are degenerate.
        """
        mid = (yes_bid + yes_ask) / 2
        if mid <= 0:
            return 0.0
        spread = yes_ask - yes_bid
        if spread <= 0:
            return 0.0
        return spread / mid * 10_000

    def _compute_depth_usd(self, volume_24h):
        """Proxy depth from 24h volume (no order book depth in payload).

        Args:
            volume_24h: 24-hour volume in USD.

        Returns:
            Float depth estimate in USD.
        """
        return float(volume_24h)

    def _compute_slippage_1k(self, spread_bps, depth_usd):
        """Estimate cost fraction for a $1K order.

        Uses half-spread cost + linear market impact from depth.

        Args:
            spread_bps: Spread in basis points.
            depth_usd: Depth proxy in USD.

        Returns:
            Float fraction (e.g. 0.006 = 0.6% cost).
        """
        half_spread_frac = spread_bps / 10_000 / 2
        market_impact_frac = 1_000 / max(depth_usd, 1_000)
        return half_spread_frac + market_impact_frac

    def _compute_liquidity_score(self, volume_24h):
        """Log-scaled liquidity score from 24h volume, 0-100.

        Mapping: ~$10 → 0, ~$100 → 33, ~$1K → 67, ~$10K → 100.

        Args:
            volume_24h: 24-hour volume in USD.

        Returns:
            Float in [0, 100].
        """
        raw = 100 * (math.log10(max(volume_24h, 0.01)) - 1) / 3
        return max(0.0, min(100.0, raw))

    def _compute_executability_score(self, volume_24h, spread_bps):
        """Composite executability score (0-100), volume-primary spread-penalized.

        Formula:
            volume_score   = clip(100 * (log10(volume_24h) - 1) / 3, 0, 100)
            spread_penalty = clip(spread_bps / 300, 0, 1) * 40
            score          = max(0, volume_score - spread_penalty)

        Verified:
            volume=50,   spread=0 bps   → 23.3 < 40  (illiquid market)
            volume=5000, spread=100 bps → 76.7 > 70  (liquid market)

        Args:
            volume_24h: 24-hour volume in USD.
            spread_bps: Spread in basis points.

        Returns:
            Float in [0, 100].
        """
        volume_score = max(0.0, min(100.0, 100 * (math.log10(max(volume_24h, 0.01)) - 1) / 3))
        spread_penalty = min(1.0, spread_bps / 300) * 40
        return max(0.0, volume_score - spread_penalty)

    # ------------------------------------------------------------------
    # Pipeline methods
    # ------------------------------------------------------------------

    def process_event(self, price_payload):
        """Compute all microstructure metrics from a feed:price_update payload.

        Args:
            price_payload: Dict matching the feed:price_update schema.

        Returns:
            Dict with keys: market_id, platform, spread_bps, depth_usd,
            slippage_1k, liquidity_score, executability_score.
        """
        market_id = price_payload.get("market_id", "")
        platform = price_payload.get("platform", "polymarket")
        yes_bid = float(price_payload.get("yes_bid", 0.0))
        yes_ask = float(price_payload.get("yes_ask", 0.0))
        volume_24h = float(price_payload.get("volume_24h", 0.0))

        spread_bps = self._compute_spread_bps(yes_bid, yes_ask)
        depth_usd = self._compute_depth_usd(volume_24h)
        slippage_1k = self._compute_slippage_1k(spread_bps, depth_usd)
        liquidity_score = self._compute_liquidity_score(volume_24h)
        executability_score = self._compute_executability_score(volume_24h, spread_bps)

        return {
            "market_id": market_id,
            "platform": platform,
            "spread_bps": spread_bps,
            "depth_usd": depth_usd,
            "slippage_1k": slippage_1k,
            "liquidity_score": liquidity_score,
            "executability_score": executability_score,
        }

    def update(self, market_id, structure):
        """Persist structure and publish bus events.

        Always publishes `signal:market_structure` (overwrite mode via bus).
        Publishes `market:illiquid` when executability_score < ILLIQUID_THRESHOLD.

        Args:
            market_id: Market identifier.
            structure: Structure dict from process_event().
        """
        self._state_cache[market_id] = structure
        self.store.write_json(STATE_FILE, self._state_cache)

        self.bus.publish(
            topic="signal:market_structure",
            producer="POLY_MARKET_STRUCTURE_ANALYZER",
            payload=structure,
            priority="normal",
        )

        if structure["executability_score"] < ILLIQUID_THRESHOLD:
            logger.warning(
                "ILLIQUID %s — executability=%.1f spread=%.1f bps depth=$%.0f",
                market_id,
                structure["executability_score"],
                structure["spread_bps"],
                structure["depth_usd"],
            )
            self.bus.publish(
                topic="market:illiquid",
                producer="POLY_MARKET_STRUCTURE_ANALYZER",
                payload={
                    "market_id": market_id,
                    "platform": structure.get("platform", "polymarket"),
                    "executability_score": structure["executability_score"],
                    "spread_bps": structure["spread_bps"],
                    "depth_usd": structure["depth_usd"],
                    "reason": "low_liquidity",
                },
                priority="normal",
            )
