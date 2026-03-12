"""Tests for POLY_DATA_VALIDATOR."""

import json
import os
import tempfile
import unittest

from agents.poly_data_validator import PolyDataValidator


def _make_validator(tmp_dir, rules_override=None):
    """Create a PolyDataValidator with a temp state directory."""
    rules_path = os.path.join(tmp_dir, "validation_rules.json")
    rules = {
        "price": {
            "min_price": 0.01,
            "max_price": 0.99,
            "sum_min": 0.95,
            "sum_max": 1.05,
            "max_variation_pct": 30,
        },
        "binance": {
            "min_price": 0,
            "max_variation_pct": 5,
        },
        "noaa": {
            "min_temp_f": -50,
            "max_temp_f": 140,
            "min_confidence": 0.0,
            "max_confidence": 1.0,
        },
        "wallet": {
            "max_positions_per_wallet": 200,
            "min_position_size": 0,
            "min_avg_price": 0,
        },
        "alert_after_consecutive_failures": 5,
    }
    if rules_override:
        rules.update(rules_override)
    with open(rules_path, "w") as f:
        json.dump(rules, f)

    state_dir = os.path.join(tmp_dir, "state")
    return PolyDataValidator(base_path=state_dir, rules_path=rules_path)


# --- Valid payloads ---

VALID_PRICE = {
    "market_id": "0xabc",
    "platform": "polymarket",
    "yes_price": 0.62,
    "no_price": 0.39,
    "yes_ask": 0.63,
    "yes_bid": 0.61,
    "no_ask": 0.40,
    "no_bid": 0.38,
    "volume_24h": 125000,
    "data_status": "VALID",
}

VALID_BINANCE = {
    "symbol": "BTCUSDT",
    "price": 98432.50,
    "bids_top5": [[98430, 1.2], [98428, 0.8]],
    "asks_top5": [[98435, 0.9], [98437, 1.1]],
    "last_trade_qty": 0.15,
    "data_status": "VALID",
}

VALID_NOAA = {
    "station": "KLGA",
    "city": "New York",
    "daily_max_forecast_f": 82,
    "confidence": 0.92,
    "forecast_timestamp": "2026-04-20T12:00:00Z",
    "data_status": "VALID",
}

VALID_WALLET = {
    "wallet": "0x1234",
    "positions": [
        {"market_id": "0xabc", "side": "YES", "size": 500, "avg_price": 0.45},
    ],
    "data_status": "VALID",
}


# ===== Price validation =====

class TestPriceValidation(unittest.TestCase):
    def test_valid_price_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            is_valid, issues = v.validate_price(VALID_PRICE)
            self.assertTrue(is_valid)
            self.assertEqual(issues, [])

    def test_price_zero_suspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_PRICE, "yes_price": 0.00}
            is_valid, issues = v.validate_price(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "price_range" for i in issues))

    def test_price_out_of_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_PRICE, "yes_price": 1.50}
            is_valid, issues = v.validate_price(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "price_range" for i in issues))

    def test_price_sum_out_of_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_PRICE, "yes_price": 0.40, "no_price": 0.40}
            is_valid, issues = v.validate_price(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "price_sum" for i in issues))

    def test_price_variation_too_high(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            # First call to establish baseline
            v.validate_price(VALID_PRICE)
            # Second call with huge jump
            payload = {**VALID_PRICE, "yes_price": 0.10, "no_price": 0.91}
            is_valid, issues = v.validate_price(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "price_variation" for i in issues))

    def test_price_stale_suspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_PRICE, "data_status": "STALE"}
            is_valid, issues = v.validate_price(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "stale_data" for i in issues))


# ===== Binance validation =====

class TestBinanceValidation(unittest.TestCase):
    def test_valid_binance_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            is_valid, issues = v.validate_binance(VALID_BINANCE)
            self.assertTrue(is_valid)
            self.assertEqual(issues, [])

    def test_binance_price_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_BINANCE, "price": 0}
            is_valid, issues = v.validate_binance(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "price_zero" for i in issues))

    def test_binance_empty_orderbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_BINANCE, "bids_top5": [], "asks_top5": []}
            is_valid, issues = v.validate_binance(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "empty_orderbook" for i in issues))

    def test_binance_variation_too_high(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            # Establish baseline
            v.validate_binance(VALID_BINANCE)
            # 10% jump
            payload = {**VALID_BINANCE, "price": 108275.75}
            is_valid, issues = v.validate_binance(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "price_variation" for i in issues))


# ===== NOAA validation =====

class TestNoaaValidation(unittest.TestCase):
    def test_valid_noaa_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            is_valid, issues = v.validate_noaa(VALID_NOAA)
            self.assertTrue(is_valid)
            self.assertEqual(issues, [])

    def test_noaa_temp_out_of_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_NOAA, "daily_max_forecast_f": 200}
            is_valid, issues = v.validate_noaa(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "temp_range" for i in issues))

    def test_noaa_confidence_out_of_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_NOAA, "confidence": 1.5}
            is_valid, issues = v.validate_noaa(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "confidence_range" for i in issues))

    def test_noaa_stale_suspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_NOAA, "data_status": "STALE"}
            is_valid, issues = v.validate_noaa(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "stale_data" for i in issues))

    def test_noaa_temp_none_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_NOAA, "daily_max_forecast_f": None}
            is_valid, issues = v.validate_noaa(payload)
            self.assertTrue(is_valid)


# ===== Wallet validation =====

class TestWalletValidation(unittest.TestCase):
    def test_valid_wallet_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            is_valid, issues = v.validate_wallet(VALID_WALLET)
            self.assertTrue(is_valid)
            self.assertEqual(issues, [])

    def test_wallet_negative_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {
                **VALID_WALLET,
                "positions": [
                    {"market_id": "0xabc", "side": "YES", "size": -10, "avg_price": 0.45},
                ],
            }
            is_valid, issues = v.validate_wallet(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "negative_size" for i in issues))

    def test_wallet_spam(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            positions = [
                {"market_id": f"0x{i:04x}", "side": "YES", "size": 10, "avg_price": 0.5}
                for i in range(250)
            ]
            payload = {**VALID_WALLET, "positions": positions}
            is_valid, issues = v.validate_wallet(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "spam_detection" for i in issues))

    def test_wallet_stale_suspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_WALLET, "data_status": "STALE"}
            is_valid, issues = v.validate_wallet(payload)
            self.assertFalse(is_valid)
            self.assertTrue(any(i["check_failed"] == "stale_data" for i in issues))

    def test_wallet_empty_positions_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            payload = {**VALID_WALLET, "positions": []}
            is_valid, issues = v.validate_wallet(payload)
            self.assertTrue(is_valid)


# ===== Integration =====

class TestProcessEvent(unittest.TestCase):
    def test_process_event_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            event = {"topic": "feed:price_update", "payload": VALID_PRICE}
            result = v.process_event(event)
            self.assertEqual(result["status"], "VALID")
            self.assertEqual(result["issues"], [])

    def test_process_event_suspect_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            bad_payload = {**VALID_PRICE, "yes_price": 0.00}
            event = {"topic": "feed:price_update", "payload": bad_payload}
            result = v.process_event(event)

            self.assertEqual(result["status"], "SUSPECT")

            events = v.bus.poll("test_consumer", topics=["data:validation_failed"])
            self.assertGreaterEqual(len(events), 1)
            evt = events[0]
            self.assertEqual(evt["topic"], "data:validation_failed")
            self.assertEqual(evt["producer"], "POLY_DATA_VALIDATOR")
            self.assertEqual(evt["payload"]["source"], "POLY_MARKET_CONNECTOR")

    def test_consecutive_failures_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            bad_payload = {**VALID_PRICE, "yes_price": 0.00}
            event = {"topic": "feed:price_update", "payload": bad_payload}

            for i in range(5):
                v.process_event(event)

            events = v.bus.poll("test_consumer", topics=["data:validation_failed"])
            # Last event should have consecutive_failures >= 5
            last_evt = events[-1]
            self.assertGreaterEqual(
                last_evt["payload"]["consecutive_failures"], 5
            )

    def test_success_resets_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            bad_payload = {**VALID_PRICE, "yes_price": 0.00}
            bad_event = {"topic": "feed:price_update", "payload": bad_payload}

            # 3 failures
            for _ in range(3):
                v.process_event(bad_event)

            source_key = "price:0xabc"
            self.assertEqual(v._failure_counts.get(source_key, 0), 3)

            # 1 success resets
            good_event = {"topic": "feed:price_update", "payload": VALID_PRICE}
            v.process_event(good_event)
            self.assertEqual(v._failure_counts.get(source_key, 0), 0)

    def test_validate_routes_by_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)

            topics_and_payloads = [
                ("feed:price_update", VALID_PRICE),
                ("feed:binance_update", VALID_BINANCE),
                ("feed:noaa_update", VALID_NOAA),
                ("feed:wallet_update", VALID_WALLET),
            ]
            for topic, payload in topics_and_payloads:
                result = v.validate(topic, payload)
                self.assertEqual(
                    result["status"], "VALID",
                    f"Expected VALID for {topic}, got {result}",
                )

    def test_unknown_topic_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            result = v.validate("unknown:topic", {"foo": "bar"})
            self.assertEqual(result["status"], "VALID")

    def test_validation_rules_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_validator(tmp)
            self.assertIn("price", v.rules)
            self.assertIn("binance", v.rules)
            self.assertIn("noaa", v.rules)
            self.assertIn("wallet", v.rules)
            self.assertEqual(v.rules["price"]["min_price"], 0.01)


if __name__ == "__main__":
    unittest.main()
