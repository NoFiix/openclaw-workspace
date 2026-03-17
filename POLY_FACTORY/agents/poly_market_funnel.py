"""
POLY_MARKET_FUNNEL — Deterministic pre-filter for LLM pipeline.

Reads active_markets_full.json (all markets from connector).
Cross-references polymarket_prices.json for yes_price data.
Applies 4 deterministic filters to produce a shortlist.
Writes active_markets.json (shortlist for market_analyst LLM pipeline).

Filters (in order):
  F1: volume_24h >= MIN_VOLUME_24H
  F2: days_to_expiry in [MIN_DAYS_TO_EXPIRY, MAX_DAYS_TO_EXPIRY]
  F3: yes_price in [MIN_PRICE, MAX_PRICE]
  F4: executability_score >= MIN_EXECUTABILITY_SCORE

No LLM calls. No bus events. No external dependencies.
Pure deterministic JSON-in -> JSON-out.
"""

import math
import logging
from datetime import datetime, timezone

from core.poly_data_store import PolyDataStore

logger = logging.getLogger("POLY_MARKET_FUNNEL")

# State files
INPUT_FILE  = "feeds/active_markets_full.json"
PRICES_FILE = "feeds/polymarket_prices.json"
OUTPUT_FILE = "feeds/active_markets.json"

# Configurable filter thresholds
MIN_VOLUME_24H          = 5_000
MIN_PRICE               = 0.05
MAX_PRICE               = 0.90
MIN_DAYS_TO_EXPIRY      = 3
MAX_DAYS_TO_EXPIRY      = 180
MIN_EXECUTABILITY_SCORE = 30


class PolyMarketFunnel:
    """Deterministic pre-filter reducing market universe for LLM pipeline.

    Reads the full market list written by the connector and produces a
    filtered shortlist suitable for LLM analysis (market_analyst).
    Strategies that do not depend on resolution_parsed (arb_scanner,
    pair_cost, etc.) are unaffected — they read polymarket_prices.json
    which contains the full dataset.
    """

    def __init__(self, base_path="state"):
        self.store = PolyDataStore(base_path=base_path)

    # --- Pure computation helpers ---

    @staticmethod
    def _compute_executability_score(volume_24h):
        """Executability from volume only (spread=0 at this pipeline stage).

        Same formula as PolyMarketStructureAnalyzer._compute_executability_score
        with spread_bps=0.  Currently redundant with volume filter (no real
        spread data available at this pipeline stage), kept as safety net for
        when real spread data becomes available.
        """
        volume_score = max(0.0, min(100.0,
            100 * (math.log10(max(volume_24h, 0.01)) - 1) / 3))
        return volume_score

    @staticmethod
    def _parse_days_to_expiry(end_date_str):
        """Parse ISO end_date string and return days until expiry.

        Returns:
            Float days to expiry, or None if end_date is missing or unparseable.
        """
        if not end_date_str:
            return None
        try:
            end = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            return (end - datetime.now(timezone.utc)).total_seconds() / 86400
        except (ValueError, TypeError):
            return None

    # --- Main pipeline ---

    def run_once(self):
        """Read full market list, apply filters, write shortlist.

        Returns:
            List of market dicts that passed all filters.
        """
        markets = self.store.read_json(INPUT_FILE) or []
        # Assumes polymarket_prices.json uses market_id as key
        prices  = self.store.read_json(PRICES_FILE) or {}

        filtered = []
        rejected = {"f1_volume": 0, "f2_expiry": 0, "f3_price": 0, "f4_exec": 0}

        for m in markets:
            mid = m.get("market_id", "")
            vol = float(m.get("volume_24h", 0) or 0)

            # F1: Volume — minimum liquidity for tradeable markets
            if vol < MIN_VOLUME_24H:
                rejected["f1_volume"] += 1
                continue

            # F2: Expiry — reject too-soon (<3d settlement risk) and too-far (>180d capital lock)
            days = self._parse_days_to_expiry(m.get("end_date", ""))
            if days is None or not (MIN_DAYS_TO_EXPIRY <= days <= MAX_DAYS_TO_EXPIRY):
                rejected["f2_expiry"] += 1
                continue

            # F3: Price — reject extreme probabilities (LLM adds no value)
            price_data = prices.get(mid, {})
            yes_price = price_data.get("yes_ask")
            if yes_price is None:
                yes_price = price_data.get("yes_price")
            if yes_price is None:
                rejected["f3_price"] += 1
                continue
            yes_price = float(yes_price)
            if not (MIN_PRICE <= yes_price <= MAX_PRICE):
                rejected["f3_price"] += 1
                continue

            # F4: Executability — currently redundant with volume filter (no real
            # spread data yet), kept as safety net for future spread integration
            exec_score = self._compute_executability_score(vol)
            if exec_score < MIN_EXECUTABILITY_SCORE:
                rejected["f4_exec"] += 1
                continue

            filtered.append(m)

        self.store.write_json(OUTPUT_FILE, filtered)

        logger.info(
            "funnel: %d -> %d (vol:-%d exp:-%d price:-%d exec:-%d)",
            len(markets), len(filtered),
            rejected["f1_volume"], rejected["f2_expiry"],
            rejected["f3_price"], rejected["f4_exec"],
        )

        return filtered
