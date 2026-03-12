"""
POLY_ORDER_SPLITTER — Splits orders into micro-tranches calibrated by depth_usd.

Called synchronously by execution engines before placing orders.
No bus events, no audit log — pure calculation with optional market structure lookup.
"""

import math

from core.poly_data_store import PolyDataStore


TRANCHE_DEPTH_FRACTION = 0.01   # max tranche size = 1% of depth_usd
MIN_TRANCHE_EUR = 1.0           # floor: avoid dust tranches
MAX_TRANCHE_EUR = 500.0         # ceiling: cap individual tranche size
MAX_TRANCHES = 10               # never split into more than 10 tranches
DEFAULT_DEPTH_USD = 10_000.0    # fallback when market structure is unavailable

MARKET_STRUCTURE_FILE = "feeds/market_structure.json"


class PolyOrderSplitter:
    """Splits an order into micro-tranches calibrated by market depth."""

    def __init__(self, base_path="state"):
        self.store = PolyDataStore(base_path=base_path)

    def split(self, size_eur: float, price_limit: float, depth_usd: float) -> list:
        """Split an order into tranches based on market depth.

        Args:
            size_eur: Total order size in EUR.
            price_limit: Maximum acceptable fill price (same for all tranches).
            depth_usd: Market depth proxy in USD (typically 24h volume).

        Returns:
            List of tranche dicts: [{"size": float, "price_limit": float}, ...]
            Always returns at least one tranche.
        """
        if depth_usd <= 0:
            depth_usd = DEFAULT_DEPTH_USD

        max_tranche_eur = max(
            MIN_TRANCHE_EUR,
            min(MAX_TRANCHE_EUR, depth_usd * TRANCHE_DEPTH_FRACTION),
        )

        n = min(MAX_TRANCHES, max(1, math.ceil(size_eur / max_tranche_eur)))

        base_size = round(size_eur / n, 6)
        tranches = []
        allocated = 0.0

        for i in range(n):
            if i == n - 1:
                # Last tranche absorbs any rounding remainder
                tranche_size = round(size_eur - allocated, 6)
            else:
                tranche_size = base_size
                allocated = round(allocated + tranche_size, 6)
            tranches.append({"size": tranche_size, "price_limit": price_limit})

        return tranches

    def split_from_market(self, size_eur: float, price_limit: float, market_id: str) -> list:
        """Split an order using depth_usd from market_structure.json.

        Falls back to DEFAULT_DEPTH_USD if the market is not found.

        Args:
            size_eur: Total order size in EUR.
            price_limit: Maximum acceptable fill price.
            market_id: Market identifier to look up in market_structure.json.

        Returns:
            List of tranche dicts: [{"size": float, "price_limit": float}, ...]
        """
        depth_usd = DEFAULT_DEPTH_USD
        market_structure = self.store.read_json(MARKET_STRUCTURE_FILE)
        if market_structure and market_id in market_structure:
            depth_usd = float(
                market_structure[market_id].get("depth_usd", DEFAULT_DEPTH_USD)
            )
        return self.split(size_eur, price_limit, depth_usd)
