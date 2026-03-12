"""Tests for POLY_NOAA_FEED."""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from agents.poly_noaa_feed import PolyNoaaFeed, STATE_FILE


def _make_feed(tmp_dir):
    """Create a PolyNoaaFeed with a temp state directory."""
    # Write station mapping to temp location
    mapping_path = os.path.join(tmp_dir, "station_mapping.json")
    mapping = {
        "KLGA": {"city": "New York", "lat": 40.7769, "lon": -73.8740},
        "KORD": {"city": "Chicago", "lat": 41.9742, "lon": -87.9073},
        "KMIA": {"city": "Miami", "lat": 25.7959, "lon": -80.2870},
        "KDAL": {"city": "Dallas", "lat": 32.8471, "lon": -96.8518},
        "KSEA": {"city": "Seattle", "lat": 47.4502, "lon": -122.3088},
        "KATL": {"city": "Atlanta", "lat": 33.6407, "lon": -84.4277},
    }
    with open(mapping_path, "w") as f:
        json.dump(mapping, f)

    state_dir = os.path.join(tmp_dir, "state")
    return PolyNoaaFeed(base_path=state_dir, station_mapping_path=mapping_path)


# --- Mock NWS API responses ---

MOCK_OBSERVATION = {
    "properties": {
        "temperature": {"value": 27.8, "unitCode": "wmoUnit:degC"},
        "textDescription": "Partly Cloudy",
    }
}

MOCK_FORECAST = {
    "properties": {
        "periods": [
            {
                "name": "Today",
                "temperature": 82,
                "temperatureUnit": "F",
                "detailedForecast": "Partly cloudy with a high near 82.",
            },
            {
                "name": "Tonight",
                "temperature": 68,
                "temperatureUnit": "F",
                "detailedForecast": "Mostly clear.",
            },
        ]
    }
}


class TestBuildPayloadFormat(unittest.TestCase):
    def test_build_payload_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            payload = feed._build_payload(
                station="KLGA",
                city="New York",
                daily_max_f=82,
                confidence=0.92,
                timestamp="2026-04-20T12:00:00Z",
            )

            self.assertEqual(payload["station"], "KLGA")
            self.assertEqual(payload["city"], "New York")
            self.assertEqual(payload["daily_max_forecast_f"], 82)
            self.assertEqual(payload["confidence"], 0.92)
            self.assertEqual(payload["forecast_timestamp"], "2026-04-20T12:00:00Z")
            self.assertEqual(payload["data_status"], "VALID")
            self.assertEqual(len(payload), 6)


class TestFetchObservationParses(unittest.TestCase):
    def test_fetch_observation_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(feed, "_http_get", return_value=MOCK_OBSERVATION):
                result = feed.fetch_observation("KLGA")

            self.assertIn("temperature_f", result)
            # 27.8°C = 82.04°F
            self.assertAlmostEqual(result["temperature_f"], 82.0, places=0)


class TestFetchForecastParses(unittest.TestCase):
    def test_fetch_forecast_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            with patch.object(feed, "_http_get", return_value=MOCK_FORECAST):
                result = feed.fetch_forecast("KLGA")

            self.assertEqual(result["daily_max_forecast_f"], 82)
            self.assertGreater(result["confidence"], 0.0)


class TestPollOnceAllStations(unittest.TestCase):
    def test_poll_once_all_6_stations(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)

            def mock_http_get(url):
                if "observations" in url:
                    return MOCK_OBSERVATION
                return MOCK_FORECAST

            with patch.object(feed, "_http_get", side_effect=mock_http_get):
                results = feed.poll_once()

            self.assertEqual(len(results), 6)
            expected = {"KLGA", "KORD", "KMIA", "KDAL", "KSEA", "KATL"}
            self.assertEqual(set(results.keys()), expected)
            for station, payload in results.items():
                self.assertEqual(payload["data_status"], "VALID")
                self.assertIn("daily_max_forecast_f", payload)


class TestUpdateWritesState(unittest.TestCase):
    def test_update_writes_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            payload = feed._build_payload(
                station="KLGA",
                city="New York",
                daily_max_f=82,
                confidence=0.92,
                timestamp="2026-04-20T12:00:00Z",
            )

            feed.update("KLGA", payload)

            state = feed.store.read_json(STATE_FILE)
            self.assertIn("KLGA", state)
            self.assertEqual(state["KLGA"]["daily_max_forecast_f"], 82)


class TestUpdatePublishesBusEvent(unittest.TestCase):
    def test_update_publishes_bus_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            payload = feed._build_payload(
                station="KORD",
                city="Chicago",
                daily_max_f=75,
                confidence=0.90,
                timestamp="2026-04-20T12:00:00Z",
            )

            feed.update("KORD", payload)

            events = feed.bus.poll("test_consumer", topics=["feed:noaa_update"])
            self.assertGreaterEqual(len(events), 1)
            evt = events[-1]
            self.assertEqual(evt["topic"], "feed:noaa_update")
            self.assertEqual(evt["producer"], "POLY_NOAA_FEED")
            self.assertEqual(evt["payload"]["station"], "KORD")


class TestHandles503Gracefully(unittest.TestCase):
    def test_handles_503_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)

            def mock_http_503(url):
                raise ConnectionError("HTTP 503 from url: service unavailable")

            with patch.object(feed, "_http_get", side_effect=mock_http_503):
                results = feed.poll_once()

            # All stations should be present but STALE
            self.assertEqual(len(results), 6)
            for station, payload in results.items():
                self.assertEqual(payload["data_status"], "STALE")


class TestHandlesTimeoutGracefully(unittest.TestCase):
    def test_handles_timeout_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)

            def mock_timeout(url):
                raise TimeoutError("Timeout fetching url")

            with patch.object(feed, "_http_get", side_effect=mock_timeout):
                results = feed.poll_once()

            self.assertEqual(len(results), 6)
            for station, payload in results.items():
                self.assertEqual(payload["data_status"], "STALE")


class TestStationMappingLoaded(unittest.TestCase):
    def test_station_mapping_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            self.assertEqual(len(feed.stations), 6)
            expected = {"KLGA", "KORD", "KMIA", "KDAL", "KSEA", "KATL"}
            self.assertEqual(set(feed.stations.keys()), expected)


class TestIsConnected(unittest.TestCase):
    def test_is_connected_false_initially(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            self.assertFalse(feed.is_connected())

    def test_is_connected_true_after_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            payload = feed._build_payload(
                station="KLGA",
                city="New York",
                daily_max_f=82,
                confidence=0.92,
                timestamp="2026-04-20T12:00:00Z",
            )
            feed.update("KLGA", payload)
            self.assertTrue(feed.is_connected())

    def test_is_connected_false_when_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = _make_feed(tmp)
            feed._last_update_times["KLGA"] = time.time() - 600  # 10 min ago
            self.assertFalse(feed.is_connected())


if __name__ == "__main__":
    unittest.main()
