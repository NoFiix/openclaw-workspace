"""Tests for POLY_WALLET_FEED."""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from agents.poly_wallet_feed import PolyWalletFeed, STATE_FILE


TEST_WALLETS = {
    "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA": {
        "label": "Test Whale",
        "priority": "high",
    },
    "0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB": {
        "label": "Test Shark",
        "priority": "normal",
    },
    "0xCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC": {
        "label": "Test Dolphin",
        "priority": "normal",
    },
}

MOCK_GAMMA_RESPONSE = [
    {
        "conditionId": "0xmarket1aaa",
        "outcome": "Yes",
        "size": "500",
        "avgPrice": "0.45",
    },
    {
        "conditionId": "0xmarket2bbb",
        "outcome": "No",
        "size": "300",
        "avgPrice": "0.62",
    },
]

MOCK_GAMMA_RESPONSE_WRAPPED = {
    "data": [
        {
            "conditionId": "0xmarket3ccc",
            "outcome": "Yes",
            "size": "100",
            "avgPrice": "0.30",
        }
    ]
}


def _make_feed(tmp_dir, config=None):
    """Create a PolyWalletFeed with a temp state directory."""
    config_path = os.path.join(tmp_dir, "tracked_wallets.json")
    with open(config_path, "w") as f:
        json.dump(TEST_WALLETS, f)

    state_dir = os.path.join(tmp_dir, "state")
    return PolyWalletFeed(
        base_path=state_dir, wallets_config_path=config_path, config=config
    )


class TestBuildPayload(unittest.TestCase):
    def test_build_payload_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            positions = [
                {"market_id": "0xabc", "side": "YES", "size": 500, "avg_price": 0.45}
            ]
            payload = feed._build_payload("0xWALLET", positions)

            self.assertEqual(payload["wallet"], "0xWALLET")
            self.assertEqual(len(payload["positions"]), 1)
            self.assertEqual(payload["data_status"], "VALID")
            self.assertEqual(set(payload.keys()), {"wallet", "positions", "data_status"})

    def test_build_payload_empty_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            payload = feed._build_payload("0xWALLET", [])

            self.assertEqual(payload["positions"], [])
            self.assertEqual(payload["data_status"], "VALID")

    def test_build_payload_stale_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            payload = feed._build_payload("0xWALLET", [], data_status="STALE")

            self.assertEqual(payload["data_status"], "STALE")


class TestFetchPositionsGamma(unittest.TestCase):
    def test_parses_gamma_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(feed, "_http_get", return_value=MOCK_GAMMA_RESPONSE):
                positions = feed.fetch_positions_gamma("0xWALLET")

            self.assertEqual(len(positions), 2)
            self.assertEqual(positions[0]["market_id"], "0xmarket1aaa")
            self.assertEqual(positions[0]["side"], "YES")
            self.assertAlmostEqual(positions[0]["size"], 500.0)
            self.assertAlmostEqual(positions[0]["avg_price"], 0.45)
            self.assertEqual(positions[1]["side"], "NO")

    def test_parses_wrapped_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(feed, "_http_get", return_value=MOCK_GAMMA_RESPONSE_WRAPPED):
                positions = feed.fetch_positions_gamma("0xWALLET")

            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0]["market_id"], "0xmarket3ccc")

    def test_empty_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(feed, "_http_get", return_value=[]):
                positions = feed.fetch_positions_gamma("0xWALLET")

            self.assertEqual(positions, [])

    def test_connection_error_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(
                feed, "_http_get", side_effect=ConnectionError("HTTP 500")
            ):
                with self.assertRaises(ConnectionError):
                    feed.fetch_positions_gamma("0xWALLET")


class TestFetchWallet(unittest.TestCase):
    def test_uses_gamma_primary(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(feed, "_http_get", return_value=MOCK_GAMMA_RESPONSE):
                payload = feed.fetch_wallet("0xWALLET")

            self.assertEqual(payload["wallet"], "0xWALLET")
            self.assertEqual(payload["data_status"], "VALID")
            self.assertEqual(len(payload["positions"]), 2)

    def test_falls_back_to_rpc(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp, config={"polygon_rpc_url": "http://localhost:8545"})
            with patch.object(
                feed, "_http_get", side_effect=ConnectionError("Gamma down")
            ):
                payload = feed.fetch_wallet("0xWALLET")

            # RPC stub returns empty positions
            self.assertEqual(payload["wallet"], "0xWALLET")
            self.assertEqual(payload["positions"], [])
            self.assertEqual(payload["data_status"], "VALID")

    def test_both_fail_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)  # no polygon_rpc_url configured
            with patch.object(
                feed, "_http_get", side_effect=ConnectionError("Gamma down")
            ):
                with self.assertRaises(ConnectionError):
                    feed.fetch_wallet("0xWALLET")


class TestUpdate(unittest.TestCase):
    def test_writes_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            payload = feed._build_payload(
                "0xWALLET",
                [{"market_id": "0xabc", "side": "YES", "size": 500, "avg_price": 0.45}],
            )

            feed.update("0xWALLET", payload)

            state = feed.store.read_json(STATE_FILE)
            self.assertIn("0xWALLET", state)
            self.assertEqual(state["0xWALLET"]["data_status"], "VALID")
            self.assertEqual(len(state["0xWALLET"]["positions"]), 1)

    def test_publishes_bus_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            payload = feed._build_payload("0xWALLET", [])

            feed.update("0xWALLET", payload)

            events = feed.bus.poll("test_consumer", topics=["feed:wallet_update"])
            self.assertGreaterEqual(len(events), 1)
            evt = events[-1]
            self.assertEqual(evt["topic"], "feed:wallet_update")
            self.assertEqual(evt["producer"], "POLY_WALLET_FEED")
            self.assertEqual(evt["payload"]["wallet"], "0xWALLET")

    def test_updates_last_update_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            payload = feed._build_payload("0xWALLET", [])

            before = time.time()
            feed.update("0xWALLET", payload)

            self.assertIn("0xWALLET", feed._last_update_times)
            self.assertGreaterEqual(feed._last_update_times["0xWALLET"], before)

    def test_multiple_wallets_coexist(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            feed.update("0xAAA", feed._build_payload("0xAAA", []))
            feed.update("0xBBB", feed._build_payload("0xBBB", []))

            state = feed.store.read_json(STATE_FILE)
            self.assertIn("0xAAA", state)
            self.assertIn("0xBBB", state)


class TestPollOnce(unittest.TestCase):
    def test_updates_all_wallets(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(feed, "_http_get", return_value=MOCK_GAMMA_RESPONSE):
                results = feed.poll_once()

            self.assertEqual(len(results), 3)
            for wallet, payload in results.items():
                self.assertEqual(payload["data_status"], "VALID")
                self.assertEqual(len(payload["positions"]), 2)

    def test_partial_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            call_count = {"n": 0}

            def mock_http_get(url):
                call_count["n"] += 1
                if call_count["n"] <= 1:
                    return MOCK_GAMMA_RESPONSE
                raise ConnectionError("API down")

            with patch.object(feed, "_http_get", side_effect=mock_http_get):
                results = feed.poll_once()

            self.assertEqual(len(results), 3)
            valid = [p for p in results.values() if p["data_status"] == "VALID"]
            stale = [p for p in results.values() if p["data_status"] == "STALE"]
            self.assertEqual(len(valid), 1)
            self.assertEqual(len(stale), 2)

    def test_stale_does_not_overwrite_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            wallet = list(TEST_WALLETS.keys())[0]

            # First: successful update
            good_payload = feed._build_payload(
                wallet,
                [{"market_id": "0xabc", "side": "YES", "size": 500, "avg_price": 0.45}],
            )
            feed.update(wallet, good_payload)

            # Second: poll with all failures
            with patch.object(
                feed, "_http_get", side_effect=ConnectionError("API down")
            ):
                feed.poll_once()

            # State file should still have the good data
            state = feed.store.read_json(STATE_FILE)
            self.assertIn(wallet, state)
            self.assertEqual(state[wallet]["data_status"], "VALID")
            self.assertEqual(len(state[wallet]["positions"]), 1)

    def test_all_fail_all_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(
                feed, "_http_get", side_effect=ConnectionError("API down")
            ):
                results = feed.poll_once()

            self.assertEqual(len(results), 3)
            for payload in results.values():
                self.assertEqual(payload["data_status"], "STALE")


class TestHandlesErrors(unittest.TestCase):
    def test_handles_connection_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(
                feed, "_http_get", side_effect=ConnectionError("HTTP 503")
            ):
                results = feed.poll_once()

            self.assertEqual(len(results), 3)
            for payload in results.values():
                self.assertEqual(payload["data_status"], "STALE")

    def test_handles_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(
                feed, "_http_get", side_effect=TimeoutError("Timeout")
            ):
                results = feed.poll_once()

            self.assertEqual(len(results), 3)
            for payload in results.values():
                self.assertEqual(payload["data_status"], "STALE")


class TestWalletConfig(unittest.TestCase):
    def test_wallet_config_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            self.assertEqual(len(feed.wallets), 3)
            expected = set(TEST_WALLETS.keys())
            self.assertEqual(set(feed.wallets.keys()), expected)


class TestIsConnected(unittest.TestCase):
    def test_false_initially(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            self.assertFalse(feed.is_connected())

    def test_true_after_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            feed.update("0xWALLET", feed._build_payload("0xWALLET", []))
            self.assertTrue(feed.is_connected())

    def test_false_when_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            feed._last_update_times["0xWALLET"] = time.time() - 300  # 5 min ago
            self.assertFalse(feed.is_connected())


if __name__ == "__main__":
    unittest.main()
