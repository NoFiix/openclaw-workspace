"""
POLY_WEATHER_ARB — NOAA forecast vs Polymarket weather bucket arbitrage strategy.

Consumes feed:noaa_update and feed:price_update events.
Emits trade:signal when NOAA confidence exceeds the Polymarket YES ask price for
the matching temperature bucket by more than EDGE_THRESHOLD.

This module contains ONLY signal logic. No execution, no order routing.
"""

import json
import os

from core.poly_audit_log import PolyAuditLog
from core.poly_event_bus import PolyEventBus


CONSUMER_ID = "POLY_WEATHER_ARB"
ACCOUNT_ID = "ACC_POLY_WEATHER_ARB"
PLATFORM = "polymarket"

# Strategy parameters
EDGE_THRESHOLD = 0.15       # min (noaa_confidence - yes_ask) to emit a signal
MIN_NOAA_CONFIDENCE = 0.70  # ignore low-confidence forecasts
SUGGESTED_SIZE_EUR = 25.0   # suggested order size before Kelly sizing


class PolyWeatherArb:
    """Weather arbitrage strategy.

    Detects mispriced Polymarket temperature-bucket markets by comparing NOAA
    daily-max temperature forecasts to the current YES ask price of the matching
    bucket. A signal is emitted when:
        noaa_confidence - yes_ask > EDGE_THRESHOLD
    and the forecast confidence meets MIN_NOAA_CONFIDENCE.
    """

    def __init__(self, base_path="state", mapping_path=None):
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)

        if mapping_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            mapping_path = os.path.join(
                project_root, "references", "weather_market_mapping.json"
            )

        with open(mapping_path, "r", encoding="utf-8") as f:
            self._mapping = json.load(f)

        self._noaa_cache = {}   # station -> latest noaa payload
        self._price_cache = {}  # market_id -> latest price payload

    # ------------------------------------------------------------------
    # Pure helpers
    # ------------------------------------------------------------------

    def _get_bucket(self, temp_f, buckets: list):
        """Return the bucket dict whose temperature range contains temp_f.

        Bucket boundaries:
          - min_f=None          → open lower bound  (temp_f < max_f)
          - max_f=None          → open upper bound  (temp_f >= min_f)
          - both set            → half-open [min_f, max_f)

        Args:
            temp_f: Forecast temperature in °F.
            buckets: List of bucket dicts from the mapping.

        Returns:
            Matching bucket dict, or None if no match.
        """
        for bucket in buckets:
            min_f = bucket.get("min_f")
            max_f = bucket.get("max_f")
            if min_f is None and max_f is not None:
                if temp_f < max_f:
                    return bucket
            elif max_f is None and min_f is not None:
                if temp_f >= min_f:
                    return bucket
            elif min_f is not None and max_f is not None:
                if min_f <= temp_f < max_f:
                    return bucket
        return None

    def _check_opportunity(self, station: str, noaa_payload: dict) -> list:
        """Check for weather arb signals for one NOAA forecast update.

        Args:
            station: ICAO station code (e.g. "KLGA").
            noaa_payload: feed:noaa_update payload dict.

        Returns:
            List of trade:signal payload dicts (may be empty).
        """
        if noaa_payload.get("data_status") != "VALID":
            return []

        temp_f = noaa_payload.get("daily_max_forecast_f")
        noaa_confidence = noaa_payload.get("confidence", 0.0)

        if temp_f is None or noaa_confidence < MIN_NOAA_CONFIDENCE:
            return []

        station_data = self._mapping.get(station)
        if not station_data:
            return []

        signals = []

        for market in station_data.get("markets", []):
            bucket = self._get_bucket(temp_f, market.get("buckets", []))
            if bucket is None:
                continue

            bucket_market_id = bucket.get("market_id")
            if not bucket_market_id:
                continue

            price_data = self._price_cache.get(bucket_market_id)
            if price_data is None:
                continue

            yes_ask = price_data.get("yes_ask")
            if yes_ask is None:
                continue

            edge = noaa_confidence - yes_ask
            if edge <= EDGE_THRESHOLD:
                continue

            signals.append({
                "strategy": CONSUMER_ID,
                "account_id": ACCOUNT_ID,
                "market_id": bucket_market_id,
                "platform": PLATFORM,
                "direction": "BUY_YES",
                "confidence": round(min(1.0, noaa_confidence), 6),
                "suggested_size_eur": SUGGESTED_SIZE_EUR,
                "signal_type": "weather_arb",
                "signal_detail": {
                    "station": station,
                    "city": noaa_payload.get("city", station_data.get("city", "")),
                    "daily_max_forecast_f": temp_f,
                    "noaa_confidence": noaa_confidence,
                    "bucket_label": bucket.get("label", ""),
                    "yes_ask": yes_ask,
                    "edge": round(edge, 6),
                },
            })

        return signals

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_once(self) -> list:
        """Poll the bus, update caches, and emit signals for detected opportunities.

        Processing order within a batch (both topics are overwrite-mode, sorted by
        timestamp): price_update events typically precede noaa_update events
        (price feeds run continuously while NOAA runs every 2 min), so prices are
        in cache when the NOAA trigger is evaluated.

        Returns:
            List of trade:signal payload dicts published to the bus.
        """
        events = self.bus.poll(
            CONSUMER_ID,
            topics=["feed:noaa_update", "feed:price_update"],
        )

        signals = []

        for evt in events:
            topic = evt["topic"]
            payload = evt["payload"]

            if topic == "feed:price_update":
                mid = payload.get("market_id")
                if mid:
                    self._price_cache[mid] = payload

            elif topic == "feed:noaa_update":
                station = payload.get("station")
                if station:
                    self._noaa_cache[station] = payload
                    new_signals = self._check_opportunity(station, payload)
                    for sig in new_signals:
                        self.bus.publish("trade:signal", CONSUMER_ID, sig)
                        self.audit.log_event("trade:signal", CONSUMER_ID, sig)
                    signals.extend(new_signals)

            self.bus.ack(CONSUMER_ID, evt["event_id"])

        return signals
