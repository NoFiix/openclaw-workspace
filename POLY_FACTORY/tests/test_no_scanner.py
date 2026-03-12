"""
Tests for POLY_NO_SCANNER — LLM-powered high-probability NO opportunity scanner.

Coverage:
  - Acceptance criteria (BUY_NO conditions, rejections)
  - Payload conformance (required fields, values)
  - LLM caching (permanent — no TTL)
  - LLM response parsing (direct JSON, embedded, invalid)
  - Bus / audit integration
  - Cache behaviour (resolution / price caches)
  - Multi-market independence
"""

import json
import os
from types import SimpleNamespace

import pytest

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from strategies.poly_no_scanner import (
    ACCOUNT_ID,
    CONSUMER_ID,
    EDGE_THRESHOLD,
    LLM_CACHE_FILE,
    MAX_AMBIGUITY_SCORE,
    MIN_LLM_PROBABILITY_NO,
    MIN_NO_ASK,
    PLATFORM,
    SUGGESTED_SIZE_EUR,
    PolyNoScanner,
)


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------

class MockLLMClient:
    """Deterministic LLM stub that returns a fixed P(YES) probability."""

    def __init__(self, probability=0.05, reasoning="Very unlikely to resolve YES"):
        self.probability = probability
        self.reasoning   = reasoning
        self.call_count  = 0

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.call_count += 1
        text = json.dumps({
            "probability": self.probability,
            "reasoning":   self.reasoning,
        })
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resolution(
    market_id,
    boolean_condition="BTC > 150000 USD on 2026-03-31",
    ambiguity_score=1,
    unexpected_risk_score=2,
    source_url="https://polymarket.com/event/test",
):
    return {
        "market_id":             market_id,
        "boolean_condition":     boolean_condition,
        "ambiguity_score":       ambiguity_score,
        "unexpected_risk_score": unexpected_risk_score,
        "source_url":            source_url,
    }


def _make_price(market_id, no_ask=0.91, no_bid=0.89, yes_ask=0.09, yes_bid=0.07):
    return {
        "market_id": market_id,
        "no_ask":    no_ask,
        "no_bid":    no_bid,
        "yes_ask":   yes_ask,
        "yes_bid":   yes_bid,
    }


def _publish_resolution(bus, market_id, **kwargs):
    payload = _make_resolution(market_id, **kwargs)
    bus.publish("signal:resolution_parsed", "TEST_PRODUCER", payload)


def _publish_price(bus, market_id, no_ask=0.91):
    payload = _make_price(market_id, no_ask=no_ask)
    bus.publish("feed:price_update", "TEST_PRODUCER", payload)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scanner(tmp_path):
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.05, reasoning="Very unlikely to resolve YES")
    s = PolyNoScanner(base_path=state_path, llm_client=mock_llm)
    return s


@pytest.fixture
def scanner_and_bus(tmp_path):
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.05)
    s   = PolyNoScanner(base_path=state_path, llm_client=mock_llm)
    bus = PolyEventBus(base_path=state_path)
    return s, bus


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------

def test_buy_no_signal_when_no_ask_high_and_llm_confirms(scanner_and_bus):
    """no_ask=0.91, LLM P(YES)=0.05 → P(NO)=0.95, edge=0.04 → BUY_NO."""
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert len(signals) == 1
    assert signals[0]["direction"] == "BUY_NO"


def test_no_signal_when_no_ask_below_min(scanner_and_bus):
    """no_ask=0.85 < MIN_NO_ASK=0.90 → no signal."""
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.85)
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals == []


def test_no_signal_when_llm_prob_no_below_min(scanner_and_bus):
    """LLM P(YES)=0.15, P(NO)=0.85 < MIN_LLM_PROBABILITY_NO=0.90 → no signal."""
    s, bus = scanner_and_bus
    s._llm_client = MockLLMClient(probability=0.15)
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals == []


def test_no_signal_when_edge_below_threshold(scanner_and_bus):
    """P(NO)=0.92, no_ask=0.91 → edge=0.01 < EDGE_THRESHOLD=0.03 → no signal."""
    s, bus = scanner_and_bus
    s._llm_client = MockLLMClient(probability=0.08)  # prob_no = 0.92
    _publish_price(bus, "0xAAA", no_ask=0.91)        # edge = 0.92 - 0.91 = 0.01
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals == []


def test_no_signal_when_ambiguity_too_high(scanner_and_bus):
    """ambiguity_score = MAX_AMBIGUITY_SCORE (3) → no signal."""
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_resolution(bus, "0xAAA", ambiguity_score=MAX_AMBIGUITY_SCORE)
    signals = s.run_once()
    assert signals == []


def test_signal_when_ambiguity_just_below_max(scanner_and_bus):
    """ambiguity_score = MAX_AMBIGUITY_SCORE - 1 (2) → signal emitted."""
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_resolution(bus, "0xAAA", ambiguity_score=MAX_AMBIGUITY_SCORE - 1)
    signals = s.run_once()
    assert len(signals) == 1


# ---------------------------------------------------------------------------
# Payload conformance — top-level fields
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "strategy", "account_id", "market_id", "platform",
    "direction", "confidence", "suggested_size_eur", "signal_type", "signal_detail",
}


def _get_signal(scanner_and_bus):
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals, "Expected a signal"
    return signals[0]


def test_signal_payload_required_fields(scanner_and_bus):
    sig = _get_signal(scanner_and_bus)
    assert REQUIRED_FIELDS.issubset(sig.keys())


def test_signal_payload_strategy(scanner_and_bus):
    sig = _get_signal(scanner_and_bus)
    assert sig["strategy"] == CONSUMER_ID


def test_signal_payload_account_id(scanner_and_bus):
    sig = _get_signal(scanner_and_bus)
    assert sig["account_id"] == ACCOUNT_ID


def test_signal_payload_platform(scanner_and_bus):
    sig = _get_signal(scanner_and_bus)
    assert sig["platform"] == PLATFORM


def test_signal_payload_direction_is_buy_no(scanner_and_bus):
    sig = _get_signal(scanner_and_bus)
    assert sig["direction"] == "BUY_NO"


def test_signal_payload_signal_type(scanner_and_bus):
    sig = _get_signal(scanner_and_bus)
    assert sig["signal_type"] == "no_scanner"


def test_signal_payload_suggested_size_eur(scanner_and_bus):
    sig = _get_signal(scanner_and_bus)
    assert sig["suggested_size_eur"] == SUGGESTED_SIZE_EUR


def test_signal_confidence_in_range(scanner_and_bus):
    sig = _get_signal(scanner_and_bus)
    assert 0.0 <= sig["confidence"] <= 1.0


def test_signal_confidence_not_above_1(scanner_and_bus):
    """Extreme edge: very high P(NO), very low no_ask → confidence clamped at 1.0."""
    s, bus = scanner_and_bus
    s._llm_client = MockLLMClient(probability=0.01)  # P(NO) = 0.99
    _publish_price(bus, "0xAAA", no_ask=0.90)         # edge = 0.09, well above 4×threshold
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals[0]["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Signal detail fields and values
# ---------------------------------------------------------------------------

REQUIRED_DETAIL_FIELDS = {
    "boolean_condition", "prob_yes", "prob_no", "no_ask",
    "edge", "ambiguity_score", "unexpected_risk_score", "reasoning",
}


def test_signal_detail_fields(scanner_and_bus):
    sig = _get_signal(scanner_and_bus)
    assert REQUIRED_DETAIL_FIELDS.issubset(sig["signal_detail"].keys())


def test_signal_detail_values(scanner_and_bus):
    s, bus = scanner_and_bus
    COND   = "BTC price > 150000 USD on 2026-03-31"
    NO_ASK = 0.91
    _publish_price(bus, "0xAAA", no_ask=NO_ASK)
    _publish_resolution(bus, "0xAAA", boolean_condition=COND, ambiguity_score=1, unexpected_risk_score=2)
    signals = s.run_once()
    detail = signals[0]["signal_detail"]
    assert detail["boolean_condition"] == COND
    assert detail["no_ask"] == NO_ASK
    assert detail["ambiguity_score"] == 1
    assert detail["unexpected_risk_score"] == 2
    assert abs(detail["prob_yes"] - 0.05) < 1e-5
    assert abs(detail["prob_no"] - 0.95) < 1e-5
    assert abs(detail["edge"] - (0.95 - NO_ASK)) < 1e-4
    assert detail["reasoning"] == "Very unlikely to resolve YES"


# ---------------------------------------------------------------------------
# LLM caching — permanent (no TTL)
# ---------------------------------------------------------------------------

def test_llm_cache_hit_no_new_call(tmp_path):
    """Pre-seeded cache should prevent LLM call (permanent cache)."""
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.05)
    s = PolyNoScanner(base_path=state_path, llm_client=mock_llm)

    # Pre-seed cache entry — no timestamp needed (permanent)
    s._llm_cache["0xAAA"] = {
        "prob_yes":  0.05,
        "reasoning": "Cached",
    }

    res_payload   = _make_resolution("0xAAA")
    price_payload = _make_price("0xAAA", no_ask=0.91)
    s._check_opportunity("0xAAA", res_payload, price_payload)

    assert mock_llm.call_count == 0


def test_llm_cache_no_ttl(tmp_path):
    """Pre-seeded cache with any timestamp is still valid (permanent, no TTL)."""
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.05)
    s = PolyNoScanner(base_path=state_path, llm_client=mock_llm)

    # Even with timestamp=0 (Unix epoch), should still be a cache hit
    s._llm_cache["0xAAA"] = {
        "prob_yes":  0.05,
        "reasoning": "Very old entry",
        "timestamp": 0,
    }

    res_payload   = _make_resolution("0xAAA")
    price_payload = _make_price("0xAAA", no_ask=0.91)
    s._check_opportunity("0xAAA", res_payload, price_payload)

    assert mock_llm.call_count == 0


def test_llm_cache_persisted_to_disk(scanner_and_bus, tmp_path):
    """After a signal is emitted, the LLM cache file should exist on disk."""
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_resolution(bus, "0xAAA")
    s.run_once()

    cache_path = os.path.join(s.store.base_path, LLM_CACHE_FILE)
    assert os.path.exists(cache_path), "LLM cache file not found"
    with open(cache_path) as f:
        data = json.load(f)
    assert "0xAAA" in data


def test_llm_cache_loaded_on_init(tmp_path):
    """A pre-written cache file should be loaded by a new scanner instance."""
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.05)

    # Write cache file manually
    ds = PolyDataStore(base_path=state_path)
    ds.write_json(LLM_CACHE_FILE, {
        "0xAAA": {"prob_yes": 0.05, "reasoning": "Preloaded"},
    })

    s = PolyNoScanner(base_path=state_path, llm_client=mock_llm)

    res_payload   = _make_resolution("0xAAA")
    price_payload = _make_price("0xAAA", no_ask=0.91)
    s._check_opportunity("0xAAA", res_payload, price_payload)

    assert mock_llm.call_count == 0, "Should have used the loaded disk cache"


# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------

def test_parse_llm_response_direct_json(scanner):
    raw = json.dumps({"probability": 0.04, "reasoning": "Very unlikely condition"})
    prob_yes, reasoning = scanner._parse_llm_response(raw)
    assert abs(prob_yes - 0.04) < 1e-9
    assert reasoning == "Very unlikely condition"


def test_parse_llm_response_embedded_in_prose(scanner):
    raw = 'Based on the analysis: {"probability": 0.06, "reasoning": "Unlikely"} seems right.'
    prob_yes, reasoning = scanner._parse_llm_response(raw)
    assert abs(prob_yes - 0.06) < 1e-9
    assert reasoning == "Unlikely"


def test_parse_llm_response_invalid_raises(scanner):
    with pytest.raises(ValueError):
        scanner._parse_llm_response("This is not JSON at all.")


# ---------------------------------------------------------------------------
# Bus / audit integration
# ---------------------------------------------------------------------------

def test_signal_published_to_bus(scanner_and_bus):
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_resolution(bus, "0xAAA")
    s.run_once()

    events = bus.poll("TEST_CHECKER", topics=["trade:signal"])
    assert any(
        e["topic"] == "trade:signal" and e["payload"].get("strategy") == CONSUMER_ID
        for e in events
    )


def test_signal_bus_producer(scanner_and_bus):
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_resolution(bus, "0xAAA")
    s.run_once()

    events = bus.poll("TEST_CHECKER2", topics=["trade:signal"])
    trade_events = [e for e in events if e["topic"] == "trade:signal"]
    assert len(trade_events) >= 1
    assert trade_events[0]["producer"] == CONSUMER_ID


def test_signal_audit_logged(scanner_and_bus):
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_resolution(bus, "0xAAA")
    s.run_once()

    audit_dir = os.path.join(s.store.base_path, "audit")
    assert os.path.isdir(audit_dir), "Audit directory not created"
    audit_files = [f for f in os.listdir(audit_dir) if f.startswith("audit_") and f.endswith(".jsonl")]
    assert audit_files, "No audit log file found"
    topics = []
    for fname in audit_files:
        with open(os.path.join(audit_dir, fname)) as f:
            for line in f:
                topics.append(json.loads(line)["topic"])
    assert "trade:signal" in topics


def test_run_once_acks_events(scanner_and_bus):
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_resolution(bus, "0xAAA")
    s.run_once()

    # Second run_once: events acked → no new events polled → updated_markets empty → no signals.
    second_signals = s.run_once()
    assert second_signals == []


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

def test_resolution_cache_updated_on_event(scanner_and_bus):
    s, bus = scanner_and_bus
    _publish_resolution(bus, "0xAAA")
    s.run_once()
    assert "0xAAA" in s._resolution_cache


def test_price_cache_updated_on_event(scanner_and_bus):
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    s.run_once()
    assert "0xAAA" in s._price_cache
    assert s._price_cache["0xAAA"]["no_ask"] == 0.91


def test_no_signal_without_price_cache(scanner_and_bus):
    s, bus = scanner_and_bus
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals == []


def test_no_signal_without_resolution_cache(scanner_and_bus):
    s, bus = scanner_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.91)
    signals = s.run_once()
    assert signals == []


# ---------------------------------------------------------------------------
# Multi-market independence
# ---------------------------------------------------------------------------

def test_multiple_markets_both_signal(scanner_and_bus):
    s, bus = scanner_and_bus
    # Both markets: P(YES)=0.05, no_ask=0.93 → P(NO)=0.95, edge=0.02... wait
    # edge = 0.95 - 0.93 = 0.02 < EDGE_THRESHOLD(0.03) — need higher edge
    # Use no_ask=0.91: edge = 0.95 - 0.91 = 0.04 > 0.03 ✓
    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_price(bus, "0xBBB", no_ask=0.91)
    _publish_resolution(bus, "0xAAA")
    _publish_resolution(bus, "0xBBB")
    signals = s.run_once()
    market_ids = {sig["market_id"] for sig in signals}
    assert "0xAAA" in market_ids
    assert "0xBBB" in market_ids


def test_multiple_markets_only_one_signals(tmp_path):
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.05)
    s   = PolyNoScanner(base_path=state_path, llm_client=mock_llm)
    bus = PolyEventBus(base_path=state_path)

    # Pre-seed LLM cache for deterministic results
    # 0xAAA: P(YES)=0.05 → P(NO)=0.95, no_ask=0.91, edge=0.04 > 0.03 → signal
    # 0xBBB: P(YES)=0.15 → P(NO)=0.85 < MIN_LLM_PROBABILITY_NO=0.90 → no signal
    s._llm_cache["0xAAA"] = {"prob_yes": 0.05, "reasoning": "high NO prob"}
    s._llm_cache["0xBBB"] = {"prob_yes": 0.15, "reasoning": "low NO prob"}

    _publish_price(bus, "0xAAA", no_ask=0.91)
    _publish_price(bus, "0xBBB", no_ask=0.91)
    _publish_resolution(bus, "0xAAA")
    _publish_resolution(bus, "0xBBB")

    signals = s.run_once()
    assert len(signals) == 1
    assert signals[0]["market_id"] == "0xAAA"
