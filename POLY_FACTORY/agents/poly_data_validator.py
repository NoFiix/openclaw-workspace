"""
POLY_DATA_VALIDATOR — Data quality filter for POLY_FACTORY.

Validates all incoming feed data before it reaches strategies.
Marks data VALID or SUSPECT. Publishes data:validation_failed on the bus
when anomalies are detected. Pure deterministic logic, no external APIs.
"""

import json
import logging
import os

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus

logger = logging.getLogger("POLY_DATA_VALIDATOR")

VALIDATION_RULES_FILE = "references/validation_rules.json"

# Topic-to-validator routing
TOPIC_VALIDATORS = {
    "feed:price_update": "price",
    "feed:binance_update": "binance",
    "feed:noaa_update": "noaa",
    "feed:wallet_update": "wallet",
}


class PolyDataValidator:
    """Data quality filter for all incoming feed data."""

    def __init__(self, base_path="state", rules_path=None):
        """Initialize the data validator.

        Args:
            base_path: Base path for state files.
            rules_path: Path to validation_rules.json. Defaults to
                references/validation_rules.json relative to project root.
        """
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)

        if rules_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            rules_path = os.path.join(project_root, VALIDATION_RULES_FILE)

        with open(rules_path, "r", encoding="utf-8") as f:
            self.rules = json.load(f)

        self._previous_values = {}
        self._failure_counts = {}

    def validate(self, topic, payload):
        """Validate a payload based on its topic.

        Args:
            topic: Bus event topic (e.g. "feed:price_update").
            payload: The event payload dict.

        Returns:
            Dict with {status: "VALID"|"SUSPECT", issues: [...]}.
        """
        validator_key = TOPIC_VALIDATORS.get(topic)
        if validator_key is None:
            return {"status": "VALID", "issues": []}

        validators = {
            "price": self.validate_price,
            "binance": self.validate_binance,
            "noaa": self.validate_noaa,
            "wallet": self.validate_wallet,
        }

        is_valid, issues = validators[validator_key](payload)
        return {
            "status": "VALID" if is_valid else "SUSPECT",
            "issues": issues,
        }

    def validate_price(self, payload):
        """Validate a feed:price_update payload.

        Returns:
            Tuple of (is_valid, issues).
        """
        rules = self.rules.get("price", {})
        min_p = rules.get("min_price", 0.01)
        max_p = rules.get("max_price", 0.99)
        sum_min = rules.get("sum_min", 0.95)
        sum_max = rules.get("sum_max", 1.05)
        max_var = rules.get("max_variation_pct", 30)

        issues = []

        if payload.get("data_status") == "STALE":
            issues.append({
                "check_failed": "stale_data",
                "reason": "data_status is STALE",
                "raw_value": "STALE",
            })

        yes_price = payload.get("yes_price", 0)
        no_price = payload.get("no_price", 0)

        if not (min_p <= yes_price <= max_p):
            issues.append({
                "check_failed": "price_range",
                "reason": f"yes_price = {yes_price} (outside [{min_p}, {max_p}])",
                "raw_value": yes_price,
            })

        if not (min_p <= no_price <= max_p):
            issues.append({
                "check_failed": "price_range",
                "reason": f"no_price = {no_price} (outside [{min_p}, {max_p}])",
                "raw_value": no_price,
            })

        price_sum = yes_price + no_price
        if not (sum_min <= price_sum <= sum_max):
            issues.append({
                "check_failed": "price_sum",
                "reason": f"yes + no = {price_sum} (outside [{sum_min}, {sum_max}])",
                "raw_value": price_sum,
            })

        # Variation check
        market_id = payload.get("market_id", "")
        cache_key = f"price:{market_id}"
        prev = self._previous_values.get(cache_key)
        if prev is not None and prev > 0:
            variation_pct = abs(yes_price - prev) / prev * 100
            if variation_pct > max_var:
                issues.append({
                    "check_failed": "price_variation",
                    "reason": f"yes_price variation {variation_pct:.1f}% > {max_var}%",
                    "raw_value": yes_price,
                })

        if not issues:
            self._previous_values[cache_key] = yes_price

        return (len(issues) == 0, issues)

    def validate_binance(self, payload):
        """Validate a feed:binance_update payload.

        Returns:
            Tuple of (is_valid, issues).
        """
        rules = self.rules.get("binance", {})
        min_p = rules.get("min_price", 0)
        max_var = rules.get("max_variation_pct", 5)

        issues = []

        if payload.get("data_status") == "STALE":
            issues.append({
                "check_failed": "stale_data",
                "reason": "data_status is STALE",
                "raw_value": "STALE",
            })

        price = payload.get("price", 0)
        if price <= min_p:
            issues.append({
                "check_failed": "price_zero",
                "reason": f"price = {price} (<= {min_p})",
                "raw_value": price,
            })

        bids = payload.get("bids_top5", [])
        asks = payload.get("asks_top5", [])
        if not bids:
            issues.append({
                "check_failed": "empty_orderbook",
                "reason": "bids_top5 is empty",
                "raw_value": [],
            })
        if not asks:
            issues.append({
                "check_failed": "empty_orderbook",
                "reason": "asks_top5 is empty",
                "raw_value": [],
            })

        # Variation check
        symbol = payload.get("symbol", "")
        cache_key = f"binance:{symbol}"
        prev = self._previous_values.get(cache_key)
        if prev is not None and prev > 0:
            variation_pct = abs(price - prev) / prev * 100
            if variation_pct > max_var:
                issues.append({
                    "check_failed": "price_variation",
                    "reason": f"price variation {variation_pct:.1f}% > {max_var}%",
                    "raw_value": price,
                })

        if not issues:
            self._previous_values[cache_key] = price

        return (len(issues) == 0, issues)

    def validate_noaa(self, payload):
        """Validate a feed:noaa_update payload.

        Returns:
            Tuple of (is_valid, issues).
        """
        rules = self.rules.get("noaa", {})
        min_temp = rules.get("min_temp_f", -50)
        max_temp = rules.get("max_temp_f", 140)
        min_conf = rules.get("min_confidence", 0.0)
        max_conf = rules.get("max_confidence", 1.0)

        issues = []

        if payload.get("data_status") == "STALE":
            issues.append({
                "check_failed": "stale_data",
                "reason": "data_status is STALE",
                "raw_value": "STALE",
            })

        temp = payload.get("daily_max_forecast_f")
        if temp is not None and not (min_temp <= temp <= max_temp):
            issues.append({
                "check_failed": "temp_range",
                "reason": f"daily_max_forecast_f = {temp} (outside [{min_temp}, {max_temp}])",
                "raw_value": temp,
            })

        confidence = payload.get("confidence", 0)
        if not (min_conf <= confidence <= max_conf):
            issues.append({
                "check_failed": "confidence_range",
                "reason": f"confidence = {confidence} (outside [{min_conf}, {max_conf}])",
                "raw_value": confidence,
            })

        return (len(issues) == 0, issues)

    def validate_wallet(self, payload):
        """Validate a feed:wallet_update payload.

        Returns:
            Tuple of (is_valid, issues).
        """
        rules = self.rules.get("wallet", {})
        max_positions = rules.get("max_positions_per_wallet", 200)
        min_size = rules.get("min_position_size", 0)
        min_price = rules.get("min_avg_price", 0)

        issues = []

        if payload.get("data_status") == "STALE":
            issues.append({
                "check_failed": "stale_data",
                "reason": "data_status is STALE",
                "raw_value": "STALE",
            })

        positions = payload.get("positions", [])

        if len(positions) > max_positions:
            issues.append({
                "check_failed": "spam_detection",
                "reason": f"{len(positions)} positions > max {max_positions}",
                "raw_value": len(positions),
            })

        for i, pos in enumerate(positions):
            size = pos.get("size", 0)
            if size < min_size:
                issues.append({
                    "check_failed": "negative_size",
                    "reason": f"position[{i}].size = {size} (< {min_size})",
                    "raw_value": size,
                })

            avg_price = pos.get("avg_price", 0)
            if avg_price < min_price:
                issues.append({
                    "check_failed": "negative_avg_price",
                    "reason": f"position[{i}].avg_price = {avg_price} (< {min_price})",
                    "raw_value": avg_price,
                })

        return (len(issues) == 0, issues)

    def _record_failure(self, source_key, issue):
        """Record a validation failure and return consecutive count.

        Args:
            source_key: Identifier for the data source.
            issue: Issue dict with check_failed, reason, raw_value.

        Returns:
            Current consecutive failure count.
        """
        self._failure_counts[source_key] = self._failure_counts.get(source_key, 0) + 1
        return self._failure_counts[source_key]

    def _reset_failure(self, source_key):
        """Reset consecutive failure counter for a source."""
        self._failure_counts[source_key] = 0

    def _publish_failure(self, source, check_failed, reason, raw_value, consecutive):
        """Publish a data:validation_failed event to the bus.

        Args:
            source: Producer name (e.g. "POLY_MARKET_CONNECTOR").
            check_failed: Name of the check that failed.
            reason: Human-readable explanation.
            raw_value: The problematic value.
            consecutive: Consecutive failure count.
        """
        self.bus.publish(
            topic="data:validation_failed",
            producer="POLY_DATA_VALIDATOR",
            payload={
                "source": source,
                "check_failed": check_failed,
                "reason": reason,
                "raw_value": raw_value,
                "consecutive_failures": consecutive,
            },
            priority="normal",
        )

    def _source_key_for_topic(self, topic, payload):
        """Derive a unique source key from topic + payload identifier."""
        if topic == "feed:price_update":
            return f"price:{payload.get('market_id', '')}"
        elif topic == "feed:binance_update":
            return f"binance:{payload.get('symbol', '')}"
        elif topic == "feed:noaa_update":
            return f"noaa:{payload.get('station', '')}"
        elif topic == "feed:wallet_update":
            return f"wallet:{payload.get('wallet', '')}"
        return f"unknown:{topic}"

    def _producer_for_topic(self, topic):
        """Map topic to its producer agent name."""
        mapping = {
            "feed:price_update": "POLY_MARKET_CONNECTOR",
            "feed:binance_update": "POLY_BINANCE_FEED",
            "feed:noaa_update": "POLY_NOAA_FEED",
            "feed:wallet_update": "POLY_WALLET_FEED",
        }
        return mapping.get(topic, "UNKNOWN")

    def process_event(self, event):
        """Full validation pipeline for a bus event.

        Args:
            event: Bus event envelope dict with topic and payload.

        Returns:
            Dict with {status, issues, source_key}.
        """
        topic = event.get("topic", "")
        payload = event.get("payload", {})

        result = self.validate(topic, payload)
        source_key = self._source_key_for_topic(topic, payload)
        source = self._producer_for_topic(topic)

        if result["status"] == "SUSPECT":
            # Increment once per failed event, then reuse count for all issues
            consecutive = self._record_failure(source_key, result["issues"][0])
            for issue in result["issues"]:
                self._publish_failure(
                    source=source,
                    check_failed=issue["check_failed"],
                    reason=issue["reason"],
                    raw_value=issue["raw_value"],
                    consecutive=consecutive,
                )
                logger.warning(
                    "SUSPECT %s: %s (consecutive: %d)",
                    source_key, issue["reason"], consecutive,
                )
        else:
            self._reset_failure(source_key)

        result["source_key"] = source_key
        return result
