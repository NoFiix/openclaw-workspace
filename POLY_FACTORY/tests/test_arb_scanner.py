"""
Tests for POLY_ARB_SCANNER (POLY-019).

Key acceptance criteria from ticket:
- Signal emitted if sum < 0.97
- No signal if sum >= 0.97
- Payload conforms to trade:signal schema
"""

import pytest

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_audit_log import PolyAuditLog
from strategies.poly_arb_scanner import (
    PolyArbScanner,
    CONSUMER_ID,
    ACCOUNT_ID,
    SUM_THRESHOLD,
    MIN_EXECUTABILITY,
    SUGGESTED_SIZE_EUR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _publish_market_structure(bus, market_id, executability_score=70):
    """Publish a signal:market_structure event."""
    bus.publish(
        topic="signal:market_structure",
        producer="POLY_MARKET_STRUCTURE_ANALYZER",
        payload={
            "market_id": market_id,
            "platform": "polymarket",
            "spread_bps": 200,
            "depth_usd": 50_000.0,
            "slippage_1k": 0.005,
            "liquidity_score": 80,
            "executability_score": executability_score,
        },
    )


def _publish_price_update(bus, market_id, yes_ask=0.47, no_ask=0.49):
    """Publish a feed:price_update event."""
    bus.publish(
        topic="feed:price_update",
        producer="POLY_MARKET_CONNECTOR",
        payload={
            "market_id": market_id,
            "platform": "polymarket",
            "yes_price": round(yes_ask - 0.01, 4),
            "no_price": round(no_ask - 0.01, 4),
            "yes_ask": yes_ask,
            "yes_bid": round(yes_ask - 0.02, 4),
            "no_ask": no_ask,
            "no_bid": round(no_ask - 0.02, 4),
            "volume_24h": 100_000,
            "data_status": "VALID",
        },
    )


@pytest.fixture
def scanner(tmp_path):
    return PolyArbScanner(base_path=str(tmp_path))


@pytest.fixture
def bus(scanner):
    return scanner.bus


# ---------------------------------------------------------------------------
# Core signal detection (ticket acceptance criteria)
# ---------------------------------------------------------------------------

def test_signal_emitted_when_sum_below_threshold(scanner, bus):
    """sum = 0.47 + 0.49 = 0.96 < 0.97 → signal emitted."""
    _publish_market_structure(bus, "0xabc", executability_score=70)
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert len(signals) == 1


def test_no_signal_when_sum_equals_threshold(scanner, bus):
    """sum = 0.97 exactly → no signal."""
    _publish_market_structure(bus, "0xabc", executability_score=70)
    _publish_price_update(bus, "0xabc", yes_ask=0.48, no_ask=0.49)  # 0.48 + 0.49 = 0.97
    signals = scanner.run_once()
    assert len(signals) == 0


def test_no_signal_when_sum_above_threshold(scanner, bus):
    """sum = 0.50 + 0.51 = 1.01 > 0.97 → no signal."""
    _publish_market_structure(bus, "0xabc", executability_score=70)
    _publish_price_update(bus, "0xabc", yes_ask=0.50, no_ask=0.51)
    signals = scanner.run_once()
    assert len(signals) == 0


def test_no_signal_low_executability(scanner, bus):
    """sum < 0.97 but executability < MIN_EXECUTABILITY → no signal."""
    _publish_market_structure(bus, "0xabc", executability_score=MIN_EXECUTABILITY - 1)
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert len(signals) == 0


def test_signal_emitted_when_executability_exactly_min(scanner, bus):
    """executability = MIN_EXECUTABILITY exactly → signal allowed."""
    _publish_market_structure(bus, "0xabc", executability_score=MIN_EXECUTABILITY)
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert len(signals) == 1


def test_no_signal_without_market_structure(scanner, bus):
    """No market_structure cached → executability defaults to 0 < 60 → no signal."""
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Payload conformance
# ---------------------------------------------------------------------------

def test_signal_payload_fields(scanner, bus):
    """All required trade:signal fields must be present."""
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    required = {
        "strategy", "account_id", "market_id", "platform",
        "direction", "confidence", "suggested_size_eur",
        "signal_type", "signal_detail",
    }
    assert required.issubset(signals[0].keys())


def test_signal_payload_strategy(scanner, bus):
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert signals[0]["strategy"] == CONSUMER_ID


def test_signal_payload_account_id(scanner, bus):
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert signals[0]["account_id"] == ACCOUNT_ID


def test_signal_payload_direction(scanner, bus):
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert signals[0]["direction"] == "BUY_YES_AND_NO"


def test_signal_payload_type(scanner, bus):
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert signals[0]["signal_type"] == "bundle_arb"


def test_signal_payload_platform(scanner, bus):
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert signals[0]["platform"] == "polymarket"


def test_signal_suggested_size_eur(scanner, bus):
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert signals[0]["suggested_size_eur"] == SUGGESTED_SIZE_EUR


def test_signal_detail_fields(scanner, bus):
    """signal_detail must contain yes_ask, no_ask, spread."""
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    detail = signals[0]["signal_detail"]
    assert "yes_ask" in detail
    assert "no_ask" in detail
    assert "spread" in detail


def test_signal_detail_values(scanner, bus):
    """signal_detail values must match the input prices."""
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    detail = signals[0]["signal_detail"]
    assert detail["yes_ask"] == 0.47
    assert detail["no_ask"] == 0.49
    expected_spread = round(SUM_THRESHOLD - (0.47 + 0.49), 6)
    assert abs(detail["spread"] - expected_spread) < 1e-9


def test_signal_spread_correct(scanner, bus):
    """spread = SUM_THRESHOLD - (yes_ask + no_ask)."""
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    expected = round(SUM_THRESHOLD - (0.47 + 0.49), 6)
    assert abs(signals[0]["signal_detail"]["spread"] - expected) < 1e-9


def test_signal_confidence_positive(scanner, bus):
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert signals[0]["confidence"] > 0


def test_signal_confidence_in_range(scanner, bus):
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert 0.0 < signals[0]["confidence"] <= 1.0


def test_signal_confidence_larger_for_lower_sum(scanner):
    """Lower ask sum → larger spread → higher confidence (pure logic check)."""
    scanner._market_structure["0xabc"] = {"executability_score": 70}
    scanner._market_structure["0xdef"] = {"executability_score": 70}

    sig_big = scanner._check_opportunity("0xabc", 0.30, 0.40)   # sum = 0.70
    sig_small = scanner._check_opportunity("0xdef", 0.47, 0.49)  # sum = 0.96

    assert sig_big is not None
    assert sig_small is not None
    assert sig_big["confidence"] > sig_small["confidence"]


# ---------------------------------------------------------------------------
# Bus and audit integration
# ---------------------------------------------------------------------------

def test_signal_published_to_bus(scanner, bus):
    """trade:signal must appear in pending_events.jsonl."""
    store = PolyDataStore(base_path=scanner.bus.store.base_path)
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    scanner.run_once()
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "trade:signal" in topics


def test_signal_audit_logged(scanner, bus):
    """trade:signal must appear in today's audit log."""
    from datetime import datetime, timezone
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    scanner.run_once()
    audit = PolyAuditLog(base_path=scanner.bus.store.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "trade:signal" in topics


def test_run_once_acks_events(scanner, bus):
    """After run_once(), a second call with same events returns nothing new."""
    _publish_market_structure(bus, "0xabc")
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    scanner.run_once()
    signals2 = scanner.run_once()
    assert signals2 == []


# ---------------------------------------------------------------------------
# Market structure caching
# ---------------------------------------------------------------------------

def test_market_structure_cached_after_run_once(scanner, bus):
    """signal:market_structure event updates internal cache."""
    _publish_market_structure(bus, "0xabc", executability_score=85)
    scanner.run_once()
    assert "0xabc" in scanner._market_structure
    assert scanner._market_structure["0xabc"]["executability_score"] == 85


def test_cache_enables_signal_on_next_run(scanner, bus):
    """Market structure published in run 1, price update in run 2 → signal on run 2."""
    _publish_market_structure(bus, "0xabc", executability_score=70)
    scanner.run_once()  # caches structure, no price update yet

    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)
    signals = scanner.run_once()
    assert len(signals) == 1


# ---------------------------------------------------------------------------
# Multi-market independence
# ---------------------------------------------------------------------------

def test_multiple_markets_only_one_signals(scanner, bus):
    """Two markets: one below threshold, one above → only one signal."""
    _publish_market_structure(bus, "0xabc", executability_score=70)
    _publish_market_structure(bus, "0xdef", executability_score=70)
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)  # sum=0.96 → signal
    _publish_price_update(bus, "0xdef", yes_ask=0.52, no_ask=0.50)  # sum=1.02 → no signal
    signals = scanner.run_once()
    assert len(signals) == 1
    assert signals[0]["market_id"] == "0xabc"


def test_multiple_markets_both_signal(scanner, bus):
    """Two markets both below threshold → two signals."""
    _publish_market_structure(bus, "0xabc", executability_score=70)
    _publish_market_structure(bus, "0xdef", executability_score=70)
    _publish_price_update(bus, "0xabc", yes_ask=0.47, no_ask=0.49)  # sum=0.96
    _publish_price_update(bus, "0xdef", yes_ask=0.45, no_ask=0.48)  # sum=0.93
    signals = scanner.run_once()
    assert len(signals) == 2
