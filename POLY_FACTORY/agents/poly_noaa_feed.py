"""
POLY_NOAA_FEED — NOAA/NWS weather forecast feed for US airport stations.

Fetches current observations and daily forecasts from the National Weather Service
API for 6 US airport stations. Writes to state/feeds/noaa_forecasts.json and
publishes feed:noaa_update on the event bus.
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

logger = logging.getLogger("POLY_NOAA_FEED")

STATE_FILE = "feeds/noaa_forecasts.json"
STATION_MAPPING_FILE = "references/station_mapping.json"
NWS_OBSERVATIONS_URL = "https://api.weather.gov/stations/{station}/observations/latest"
# Step 1: /points returns the gridpoint forecast URL in properties.forecast
NWS_POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
USER_AGENT = "POLY_FACTORY/1.0 (openclaw; weather-feed)"
HTTP_TIMEOUT = 30
FRESHNESS_THRESHOLD = 300  # 5 minutes


class PolyNoaaFeed:
    """NOAA/NWS weather forecast feed for 6 US airport stations."""

    def __init__(self, base_path="state", station_mapping_path=None):
        """Initialize the NOAA feed.

        Args:
            base_path: Base path for state files.
            station_mapping_path: Path to station_mapping.json. Defaults to
                references/station_mapping.json relative to project root.
        """
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)

        if station_mapping_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            station_mapping_path = os.path.join(project_root, STATION_MAPPING_FILE)

        with open(station_mapping_path, "r", encoding="utf-8") as f:
            self.stations = json.load(f)

        self._state_cache = {}
        self._last_update_times = {}

    def _http_get(self, url):
        """Make an HTTP GET request to NWS API and return parsed JSON.

        Args:
            url: Full URL to fetch.

        Returns:
            Parsed JSON dict.

        Raises:
            ConnectionError: On HTTP errors or network failures.
            TimeoutError: On request timeout.
        """
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/geo+json")

        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 503:
                raise ConnectionError(f"HTTP 503 from {url}: service unavailable") from e
            raise ConnectionError(f"HTTP {e.code} from {url}: {e.reason}") from e
        except urllib.error.URLError as e:
            if "timed out" in str(e.reason):
                raise TimeoutError(f"Timeout fetching {url}") from e
            raise ConnectionError(f"Connection failed to {url}: {e.reason}") from e
        except Exception as e:
            if "timed out" in str(e):
                raise TimeoutError(f"Timeout fetching {url}") from e
            raise

    def fetch_observation(self, station):
        """Fetch latest observation for a station.

        Args:
            station: ICAO station code (e.g. "KLGA").

        Returns:
            Dict with temperature_f from current observation.
        """
        url = NWS_OBSERVATIONS_URL.format(station=station)
        data = self._http_get(url)

        props = data.get("properties", {})
        temp_c = None
        temp_val = props.get("temperature", {})
        if isinstance(temp_val, dict):
            temp_c = temp_val.get("value")

        temperature_f = None
        if temp_c is not None:
            temperature_f = round(temp_c * 9 / 5 + 32, 1)

        return {"temperature_f": temperature_f}

    def fetch_forecast(self, station):
        """Fetch daily forecast for a station's coordinates.

        NWS requires a two-step fetch:
          1. GET /points/{lat},{lon}  → returns properties.forecast URL
          2. GET {forecast_url}       → returns the actual forecast periods

        Calling /points/{lat},{lon}/forecast directly returns 404.

        Args:
            station: ICAO station code (e.g. "KLGA").

        Returns:
            Dict with daily_max_forecast_f and confidence.
        """
        info = self.stations[station]
        # Step 1: resolve gridpoint and get the forecast URL
        points_url = NWS_POINTS_URL.format(lat=info["lat"], lon=info["lon"])
        points_data = self._http_get(points_url)
        forecast_url = points_data["properties"]["forecast"]
        # Step 2: fetch the actual forecast
        data = self._http_get(forecast_url)

        props = data.get("properties", {})
        periods = props.get("periods", [])

        daily_max_f = None
        confidence = 0.0

        if periods:
            first = periods[0]
            daily_max_f = first.get("temperature")
            # NWS doesn't provide confidence directly; derive from forecast detail
            detail = first.get("detailedForecast", "")
            if detail:
                confidence = 0.92
            else:
                confidence = 0.80

        return {
            "daily_max_forecast_f": daily_max_f,
            "confidence": confidence,
        }

    def fetch_station(self, station):
        """Fetch observation + forecast for a station and build payload.

        Args:
            station: ICAO station code.

        Returns:
            Payload dict for feed:noaa_update.
        """
        info = self.stations[station]
        obs = self.fetch_observation(station)
        forecast = self.fetch_forecast(station)

        return self._build_payload(
            station=station,
            city=info["city"],
            daily_max_f=forecast["daily_max_forecast_f"],
            confidence=forecast["confidence"],
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def _build_payload(self, station, city, daily_max_f, confidence, timestamp):
        """Build a feed:noaa_update payload.

        Args:
            station: ICAO station code.
            city: Human-readable city name.
            daily_max_f: Forecasted daily max temperature in Fahrenheit.
            confidence: Confidence score (0.0–1.0).
            timestamp: ISO 8601 forecast timestamp.

        Returns:
            Dict matching feed:noaa_update schema.
        """
        return {
            "station": station,
            "city": city,
            "daily_max_forecast_f": daily_max_f,
            "confidence": confidence,
            "forecast_timestamp": timestamp,
            "data_status": "VALID",
        }

    def update(self, station, payload):
        """Write payload to state file and publish bus event.

        Args:
            station: ICAO station code (key for state cache).
            payload: Dict matching feed:noaa_update schema.
        """
        self._state_cache[station] = payload
        self._last_update_times[station] = time.time()

        self.store.write_json(STATE_FILE, self._state_cache)

        self.bus.publish(
            topic="feed:noaa_update",
            producer="POLY_NOAA_FEED",
            payload=payload,
            priority="normal",
        )

    def poll_once(self):
        """Fetch all stations and update state + bus.

        Returns:
            Dict of {station: payload} for all stations.
            Failed stations get data_status "STALE".
        """
        results = {}
        for station, info in self.stations.items():
            try:
                payload = self.fetch_station(station)
                self.update(station, payload)
                results[station] = payload
            except (ConnectionError, TimeoutError) as e:
                logger.error("Failed to fetch %s: %s", station, e)
                stale_payload = self._build_payload(
                    station=station,
                    city=info["city"],
                    daily_max_f=None,
                    confidence=0.0,
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                )
                stale_payload["data_status"] = "STALE"
                results[station] = stale_payload
        return results

    def is_connected(self):
        """Check if at least 1 station was updated within the freshness threshold."""
        if not self._last_update_times:
            return False
        now = time.time()
        return any(
            (now - t) < FRESHNESS_THRESHOLD
            for t in self._last_update_times.values()
        )
