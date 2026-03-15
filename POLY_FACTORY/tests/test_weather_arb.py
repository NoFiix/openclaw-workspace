"""
Tests for POLY_WEATHER_ARB (POLY-020).

Key acceptance criteria from ticket:
- NOAA 82°F, 90% confidence + bucket YES ask 0.12 → signal
- NOAA 82°F, 90% confidence + bucket YES ask 0.85 → no signal
"""

import json
import pytest
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from strategies.poly_weather_arb import (
    PolyWeatherArb,
    CONSUMER_ID,
    ACCOUNT_ID,
    EDGE_THRESHOLD,
    MIN_NOAA_CONFIDENCE,
    SUGGESTED_SIZE_EUR,
)


# ---------------------------------------------------------------------------
# Constants for tests
# ---------------------------------------------------------------------------

BUCKET_82F_MARKET_ID = "0xklga_8084"   # 80-84°F bucket for New York


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mapping_file(tmp_path):
    """Minimal weather mapping for KLGA with 5°F buckets covering 82°F."""
    mapping = {
        "KLGA": {
            "city": "New York",
            "markets": [
                {
                    "description": "NYC daily max temperature forecast",
                    "buckets": [
                        {"label": "< 75°F",  "min_f": None, "max_f": 75, "market_id": "0xklga_lt75"},
                        {"label": "75-79°F", "min_f": 75,   "max_f": 80, "market_id": "0xklga_7579"},
                        {"label": "80-84°F", "min_f": 80,   "max_f": 85, "market_id": BUCKET_82F_MARKET_ID},
                        {"label": "85-89°F", "min_f": 85,   "max_f": 90, "market_id": "0xklga_8589"},
                        {"label": ">= 90°F", "min_f": 90,   "max_f": None, "market_id": "0xklga_ge90"},
                    ],
                }
            ],
        }
    }
    path = tmp_path / "weather_market_mapping.json"
    path.write_text(json.dumps(mapping))
    return str(path)


@pytest.fixture
def scanner(tmp_path, mapping_file):
    return PolyWeatherArb(base_path=str(tmp_path), mapping_path=mapping_file)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _publish_price(scanner, market_id=BUCKET_82F_MARKET_ID, yes_ask=0.12):
    scanner.bus.publish(
        topic="feed:price_update",
        producer="POLY_MARKET_CONNECTOR",
        payload={
            "market_id": market_id,
            "platform": "polymarket",
            "yes_price": round(yes_ask - 0.01, 4),
            "no_price": round(1.0 - yes_ask - 0.01, 4),
            "yes_ask": yes_ask,
            "yes_bid": round(yes_ask - 0.02, 4),
            "no_ask": round(1.0 - yes_ask, 4),
            "no_bid": round(1.0 - yes_ask - 0.01, 4),
            "volume_24h": 50_000,
            "data_status": "VALID",
        },
    )


def _publish_noaa(scanner, station="KLGA", temp_f=82, confidence=0.90,
                  data_status="VALID", city="New York"):
    scanner.bus.publish(
        topic="feed:noaa_update",
        producer="POLY_NOAA_FEED",
        payload={
            "station": station,
            "city": city,
            "daily_max_forecast_f": temp_f,
            "confidence": confidence,
            "forecast_timestamp": "2026-03-12T12:00:00Z",
            "data_status": data_status,
        },
    )


# ---------------------------------------------------------------------------
# Ticket acceptance criteria
# ---------------------------------------------------------------------------

def test_signal_emitted_when_bucket_price_low(scanner):
    """NOAA 82°F 90% + bucket YES ask 0.12 → signal (edge=0.78 > 0.15)."""
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner, temp_f=82, confidence=0.90)
    signals = scanner.run_once()
    assert len(signals) == 1


def test_no_signal_when_bucket_price_high(scanner):
    """NOAA 82°F 90% + bucket YES ask 0.85 → no signal (edge=0.05 ≤ 0.15)."""
    _publish_price(scanner, yes_ask=0.85)
    _publish_noaa(scanner, temp_f=82, confidence=0.90)
    signals = scanner.run_once()
    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Edge threshold boundary
# ---------------------------------------------------------------------------

def test_no_signal_when_edge_below_threshold(scanner):
    """Edge < EDGE_THRESHOLD → no signal (strictly greater than required)."""
    # yes_ask=0.83, confidence=0.90 → edge=0.07 < 0.08 → no signal
    _publish_price(scanner, yes_ask=0.83)
    _publish_noaa(scanner, temp_f=82, confidence=0.90)
    signals = scanner.run_once()
    assert len(signals) == 0


def test_signal_when_edge_just_above_threshold(scanner):
    """Edge = EDGE_THRESHOLD + epsilon → signal."""
    yes_ask = round(0.90 - EDGE_THRESHOLD - 0.001, 6)
    _publish_price(scanner, yes_ask=yes_ask)
    _publish_noaa(scanner, temp_f=82, confidence=0.90)
    signals = scanner.run_once()
    assert len(signals) == 1


# ---------------------------------------------------------------------------
# Data quality guards
# ---------------------------------------------------------------------------

def test_no_signal_when_noaa_stale(scanner):
    """data_status != 'VALID' → no signal."""
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner, temp_f=82, confidence=0.90, data_status="STALE")
    signals = scanner.run_once()
    assert len(signals) == 0


def test_no_signal_when_confidence_below_min(scanner):
    """confidence < MIN_NOAA_CONFIDENCE → no signal."""
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner, temp_f=82, confidence=MIN_NOAA_CONFIDENCE - 0.01)
    signals = scanner.run_once()
    assert len(signals) == 0


def test_signal_when_confidence_at_min(scanner):
    """confidence == MIN_NOAA_CONFIDENCE → signal allowed (if edge sufficient)."""
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner, temp_f=82, confidence=MIN_NOAA_CONFIDENCE)
    signals = scanner.run_once()
    assert len(signals) == 1


def test_no_signal_when_no_price_in_cache(scanner):
    """No price_update for the bucket market → no signal."""
    _publish_noaa(scanner, temp_f=82, confidence=0.90)
    signals = scanner.run_once()
    assert len(signals) == 0


def test_no_signal_when_station_not_in_mapping(scanner):
    """Station not in mapping → no signal."""
    _publish_price(scanner, market_id="0xunknown", yes_ask=0.10)
    _publish_noaa(scanner, station="KUNKNOWN", temp_f=82, confidence=0.90)
    signals = scanner.run_once()
    assert len(signals) == 0


def test_no_signal_when_temp_is_none(scanner):
    """daily_max_forecast_f = None → no signal."""
    scanner.bus.publish(
        topic="feed:noaa_update",
        producer="POLY_NOAA_FEED",
        payload={
            "station": "KLGA",
            "city": "New York",
            "daily_max_forecast_f": None,
            "confidence": 0.90,
            "forecast_timestamp": "2026-03-12T12:00:00Z",
            "data_status": "VALID",
        },
    )
    _publish_price(scanner, yes_ask=0.12)
    signals = scanner.run_once()
    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Payload conformance
# ---------------------------------------------------------------------------

def test_signal_payload_required_fields(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner, temp_f=82, confidence=0.90)
    signals = scanner.run_once()
    required = {
        "strategy", "account_id", "market_id", "platform",
        "direction", "confidence", "suggested_size_eur",
        "signal_type", "signal_detail",
    }
    assert required.issubset(signals[0].keys())


def test_signal_payload_strategy(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner)
    assert scanner.run_once()[0]["strategy"] == CONSUMER_ID


def test_signal_payload_account_id(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner)
    assert scanner.run_once()[0]["account_id"] == ACCOUNT_ID


def test_signal_payload_direction(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner)
    assert scanner.run_once()[0]["direction"] == "BUY_YES"


def test_signal_payload_type(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner)
    assert scanner.run_once()[0]["signal_type"] == "weather_arb"


def test_signal_payload_platform(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner)
    assert scanner.run_once()[0]["platform"] == "polymarket"


def test_signal_suggested_size_eur(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner)
    assert scanner.run_once()[0]["suggested_size_eur"] == SUGGESTED_SIZE_EUR


def test_signal_detail_fields(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner)
    detail = scanner.run_once()[0]["signal_detail"]
    for field in ("station", "city", "daily_max_forecast_f", "noaa_confidence",
                  "bucket_label", "yes_ask", "edge"):
        assert field in detail


def test_signal_detail_edge_correct(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner, confidence=0.90)
    detail = scanner.run_once()[0]["signal_detail"]
    assert abs(detail["edge"] - (0.90 - 0.12)) < 1e-6


def test_signal_confidence_matches_noaa(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner, confidence=0.85)
    assert abs(scanner.run_once()[0]["confidence"] - 0.85) < 1e-9


def test_signal_market_id_is_bucket_market_id(scanner):
    _publish_price(scanner, market_id=BUCKET_82F_MARKET_ID, yes_ask=0.12)
    _publish_noaa(scanner, temp_f=82)
    assert scanner.run_once()[0]["market_id"] == BUCKET_82F_MARKET_ID


# ---------------------------------------------------------------------------
# Bus and audit integration
# ---------------------------------------------------------------------------

def test_signal_published_to_bus(scanner):
    store = PolyDataStore(base_path=scanner.bus.store.base_path)
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner)
    scanner.run_once()
    events = store.read_jsonl("bus/pending_events.jsonl")
    assert "trade:signal" in [e.get("topic") for e in events]


def test_signal_audit_logged(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner)
    scanner.run_once()
    audit = PolyAuditLog(base_path=scanner.bus.store.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    assert "trade:signal" in [e.get("topic") for e in entries]


def test_run_once_acks_events(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner)
    scanner.run_once()
    assert scanner.run_once() == []


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

def test_price_cache_populated(scanner):
    _publish_price(scanner, market_id=BUCKET_82F_MARKET_ID, yes_ask=0.30)
    scanner.run_once()
    assert BUCKET_82F_MARKET_ID in scanner._price_cache
    assert scanner._price_cache[BUCKET_82F_MARKET_ID]["yes_ask"] == 0.30


def test_noaa_cache_populated(scanner):
    _publish_price(scanner, yes_ask=0.12)
    _publish_noaa(scanner, station="KLGA", temp_f=82)
    scanner.run_once()
    assert "KLGA" in scanner._noaa_cache
    assert scanner._noaa_cache["KLGA"]["daily_max_forecast_f"] == 82


def test_price_cache_persists_across_runs(scanner):
    """Price cached in run 1, NOAA arrives in run 2 → signal in run 2."""
    _publish_price(scanner, yes_ask=0.12)
    scanner.run_once()   # caches price, no NOAA yet

    _publish_noaa(scanner, temp_f=82, confidence=0.90)
    signals = scanner.run_once()
    assert len(signals) == 1


def test_price_and_noaa_same_batch(scanner):
    """Price published before NOAA → both in same run_once → signal."""
    _publish_price(scanner, yes_ask=0.12)       # earlier timestamp
    _publish_noaa(scanner, temp_f=82, confidence=0.90)  # later timestamp
    signals = scanner.run_once()
    assert len(signals) == 1


# ---------------------------------------------------------------------------
# Bucket logic (_get_bucket)
# ---------------------------------------------------------------------------

def test_get_bucket_lower_open(scanner):
    """Temperature below min bucket → first (open lower) bucket selected."""
    buckets = [
        {"label": "< 75°F",  "min_f": None, "max_f": 75, "market_id": "0xa"},
        {"label": "75-79°F", "min_f": 75,   "max_f": 80, "market_id": "0xb"},
        {"label": ">= 80°F", "min_f": 80,   "max_f": None, "market_id": "0xc"},
    ]
    assert scanner._get_bucket(60, buckets)["market_id"] == "0xa"


def test_get_bucket_upper_open(scanner):
    """Temperature above last fixed bucket → upper-open bucket selected."""
    buckets = [
        {"label": "< 75°F",  "min_f": None, "max_f": 75, "market_id": "0xa"},
        {"label": "75-79°F", "min_f": 75,   "max_f": 80, "market_id": "0xb"},
        {"label": ">= 80°F", "min_f": 80,   "max_f": None, "market_id": "0xc"},
    ]
    assert scanner._get_bucket(95, buckets)["market_id"] == "0xc"


def test_get_bucket_closed_range(scanner):
    """Temperature exactly at lower bound of half-open interval."""
    buckets = [
        {"label": "< 75°F",  "min_f": None, "max_f": 75, "market_id": "0xa"},
        {"label": "75-79°F", "min_f": 75,   "max_f": 80, "market_id": "0xb"},
        {"label": ">= 80°F", "min_f": 80,   "max_f": None, "market_id": "0xc"},
    ]
    assert scanner._get_bucket(75, buckets)["market_id"] == "0xb"
    assert scanner._get_bucket(79, buckets)["market_id"] == "0xb"


def test_get_bucket_boundary_upper_exclusive(scanner):
    """Temperature at upper boundary goes to next bucket (upper-exclusive)."""
    buckets = [
        {"label": "75-79°F", "min_f": 75, "max_f": 80, "market_id": "0xb"},
        {"label": "80-84°F", "min_f": 80, "max_f": 85, "market_id": "0xc"},
    ]
    assert scanner._get_bucket(80, buckets)["market_id"] == "0xc"


def test_get_bucket_returns_none_when_no_match(scanner):
    """Temperature not covered by any bucket → None."""
    buckets = [
        {"label": "75-79°F", "min_f": 75, "max_f": 80, "market_id": "0xb"},
    ]
    assert scanner._get_bucket(60, buckets) is None
    assert scanner._get_bucket(85, buckets) is None
