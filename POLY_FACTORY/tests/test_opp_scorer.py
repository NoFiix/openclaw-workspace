"""
Tests for POLY_OPP_SCORER — LLM-powered high-probability opportunity scorer.

Coverage:
  - Acceptance criteria (BUY_YES conditions, rejections)
  - Payload conformance (required fields, values)
  - LLM caching (hit / miss / persistence / load on init)
  - LLM response parsing (direct JSON, embedded, invalid)
  - Bus / audit integration
  - Cache behaviour (resolution / price caches)
  - Multi-market independence
"""

import json
import os
from types import SimpleNamespace

import pytest

from core.poly_event_bus import PolyEventBus
from strategies.poly_opp_scorer import (
    ACCOUNT_ID,
    CACHE_TTL_SECONDS,
    CONSUMER_ID,
    EDGE_THRESHOLD,
    LLM_CACHE_FILE,
    MAX_AMBIGUITY_SCORE,
    MIN_LLM_PROBABILITY,
    PLATFORM,
    SUGGESTED_SIZE_EUR,
    PolyOppScorer,
)


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------

class MockLLMClient:
    """Deterministic LLM stub that returns a fixed probability."""

    def __init__(self, probability=0.92, reasoning="Strong yes signal"):
        self.probability  = probability
        self.reasoning    = reasoning
        self.call_count   = 0

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.call_count += 1
        text = json.dumps({
            "probability": self.probability,
            "reasoning":   self.reasoning,
        })
        return SimpleNamespace(
            content=[SimpleNamespace(text=text)],
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resolution(
    market_id,
    boolean_condition="BTC > 100k on 2026-06-01",
    ambiguity_score=1,
    unexpected_risk_score=1,
    source_url="https://polymarket.com/event/test",
):
    return {
        "market_id":             market_id,
        "boolean_condition":     boolean_condition,
        "ambiguity_score":       ambiguity_score,
        "unexpected_risk_score": unexpected_risk_score,
        "source_url":            source_url,
    }


def _make_price(market_id, yes_ask=0.55, yes_bid=0.53, no_ask=0.45, no_bid=0.43):
    return {
        "market_id": market_id,
        "yes_ask":   yes_ask,
        "yes_bid":   yes_bid,
        "no_ask":    no_ask,
        "no_bid":    no_bid,
    }


def _publish_resolution(bus, market_id, **kwargs):
    payload = _make_resolution(market_id, **kwargs)
    bus.publish("signal:resolution_parsed", "TEST_PRODUCER", payload)


def _publish_price(bus, market_id, yes_ask=0.55):
    payload = _make_price(market_id, yes_ask=yes_ask)
    bus.publish("feed:price_update", "TEST_PRODUCER", payload)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scorer(tmp_path):
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.92, reasoning="Strong yes signal")
    s = PolyOppScorer(base_path=state_path, llm_client=mock_llm)
    return s


@pytest.fixture
def scorer_and_bus(tmp_path):
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.92)
    s   = PolyOppScorer(base_path=state_path, llm_client=mock_llm)
    bus = PolyEventBus(base_path=state_path)
    return s, bus


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------

def test_buy_yes_signal_when_llm_prob_high(scorer_and_bus):
    s, bus = scorer_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)      # edge = 0.92 - 0.55 = 0.37
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert len(signals) == 1
    assert signals[0]["direction"] == "BUY_YES"


def test_no_signal_when_llm_prob_below_min(scorer_and_bus):
    s, bus = scorer_and_bus
    s._llm_client = MockLLMClient(probability=0.80)  # below MIN_LLM_PROBABILITY=0.85
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals == []


def test_no_signal_when_edge_below_threshold(scorer_and_bus):
    s, bus = scorer_and_bus
    s._llm_client = MockLLMClient(probability=0.88)
    _publish_price(bus, "0xAAA", yes_ask=0.86)      # edge = 0.88 - 0.86 = 0.02 < 0.05
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals == []


def test_no_signal_when_ambiguity_too_high(scorer_and_bus):
    s, bus = scorer_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_resolution(bus, "0xAAA", ambiguity_score=MAX_AMBIGUITY_SCORE)  # = 3
    signals = s.run_once()
    assert signals == []


def test_signal_when_ambiguity_just_below_max(scorer_and_bus):
    s, bus = scorer_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_resolution(bus, "0xAAA", ambiguity_score=MAX_AMBIGUITY_SCORE - 1)  # = 2
    signals = s.run_once()
    assert len(signals) == 1


# ---------------------------------------------------------------------------
# Payload conformance — top-level fields
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "strategy", "account_id", "market_id", "platform",
    "direction", "confidence", "suggested_size_eur", "signal_type", "signal_detail",
}


def _get_signal(scorer_and_bus):
    s, bus = scorer_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals, "Expected a signal"
    return signals[0]


def test_signal_payload_required_fields(scorer_and_bus):
    sig = _get_signal(scorer_and_bus)
    assert REQUIRED_FIELDS.issubset(sig.keys())


def test_signal_payload_strategy(scorer_and_bus):
    sig = _get_signal(scorer_and_bus)
    assert sig["strategy"] == CONSUMER_ID


def test_signal_payload_account_id(scorer_and_bus):
    sig = _get_signal(scorer_and_bus)
    assert sig["account_id"] == ACCOUNT_ID


def test_signal_payload_platform(scorer_and_bus):
    sig = _get_signal(scorer_and_bus)
    assert sig["platform"] == PLATFORM


def test_signal_payload_direction_is_buy_yes(scorer_and_bus):
    sig = _get_signal(scorer_and_bus)
    assert sig["direction"] == "BUY_YES"


def test_signal_payload_signal_type(scorer_and_bus):
    sig = _get_signal(scorer_and_bus)
    assert sig["signal_type"] == "opp_scorer"


def test_signal_payload_suggested_size_eur(scorer_and_bus):
    sig = _get_signal(scorer_and_bus)
    assert sig["suggested_size_eur"] == SUGGESTED_SIZE_EUR


def test_signal_confidence_in_range(scorer_and_bus):
    sig = _get_signal(scorer_and_bus)
    assert 0.0 <= sig["confidence"] <= 1.0


def test_signal_confidence_not_above_1(scorer_and_bus):
    # Extreme edge: very large LLM prob, very low ask → confidence clamped at 1.0
    s, bus = scorer_and_bus
    s._llm_client = MockLLMClient(probability=0.99)
    _publish_price(bus, "0xAAA", yes_ask=0.01)  # edge=0.98, well above 4×threshold
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals[0]["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Signal detail fields and values
# ---------------------------------------------------------------------------

REQUIRED_DETAIL_FIELDS = {
    "boolean_condition", "llm_probability", "yes_ask",
    "edge", "ambiguity_score", "unexpected_risk_score", "reasoning",
}


def test_signal_detail_fields(scorer_and_bus):
    sig = _get_signal(scorer_and_bus)
    assert REQUIRED_DETAIL_FIELDS.issubset(sig["signal_detail"].keys())


def test_signal_detail_values(scorer_and_bus):
    s, bus = scorer_and_bus
    COND   = "ETH > 5000 USD on 2026-07-01"
    YES_ASK = 0.60
    _publish_price(bus, "0xAAA", yes_ask=YES_ASK)
    _publish_resolution(bus, "0xAAA", boolean_condition=COND, ambiguity_score=1, unexpected_risk_score=2)
    signals = s.run_once()
    detail = signals[0]["signal_detail"]
    assert detail["boolean_condition"] == COND
    assert detail["yes_ask"] == YES_ASK
    assert detail["ambiguity_score"] == 1
    assert detail["unexpected_risk_score"] == 2
    assert abs(detail["llm_probability"] - 0.92) < 1e-5
    assert abs(detail["edge"] - (0.92 - YES_ASK)) < 1e-4
    assert detail["reasoning"] == "Strong yes signal"


# ---------------------------------------------------------------------------
# LLM caching
# ---------------------------------------------------------------------------

def test_llm_cache_hit_no_new_call(tmp_path):
    """Fresh pre-seeded cache should prevent LLM call."""
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.92)
    s = PolyOppScorer(base_path=state_path, llm_client=mock_llm)

    # Pre-seed with fresh cache entry
    import time
    s._llm_cache["0xAAA"] = {
        "probability": 0.92,
        "reasoning":   "Cached",
        "timestamp":   time.time(),
    }

    res_payload   = _make_resolution("0xAAA")
    price_payload = _make_price("0xAAA", yes_ask=0.55)
    s._check_opportunity("0xAAA", res_payload, price_payload)

    assert mock_llm.call_count == 0


def test_llm_cache_miss_stale_ttl(tmp_path):
    """Stale cache entry (beyond TTL) should trigger a new LLM call."""
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.92)
    s = PolyOppScorer(base_path=state_path, llm_client=mock_llm)

    # Pre-seed with stale cache entry
    stale_ts = 0.0  # Unix epoch — far in the past
    s._llm_cache["0xAAA"] = {
        "probability": 0.92,
        "reasoning":   "Old",
        "timestamp":   stale_ts,
    }

    res_payload   = _make_resolution("0xAAA")
    price_payload = _make_price("0xAAA", yes_ask=0.55)
    s._check_opportunity("0xAAA", res_payload, price_payload)

    assert mock_llm.call_count == 1


def test_llm_cache_persisted_to_disk(scorer_and_bus, tmp_path):
    """After a signal is emitted, the LLM cache file should exist on disk."""
    s, bus = scorer_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_resolution(bus, "0xAAA")
    s.run_once()

    cache_path = os.path.join(s.store.base_path, LLM_CACHE_FILE)
    assert os.path.exists(cache_path), "LLM cache file not found"
    with open(cache_path) as f:
        data = json.load(f)
    assert "0xAAA" in data


def test_llm_cache_loaded_on_init(tmp_path):
    """A pre-written cache file should be loaded by a new scorer instance."""
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.92)

    # Write cache file manually
    store = PolyDataStore = __import__(
        "core.poly_data_store", fromlist=["PolyDataStore"]
    ).PolyDataStore
    ds = store(base_path=state_path)
    import time
    ds.write_json(LLM_CACHE_FILE, {
        "0xAAA": {"probability": 0.92, "reasoning": "Preloaded", "timestamp": time.time()},
    })

    s = PolyOppScorer(base_path=state_path, llm_client=mock_llm)

    res_payload   = _make_resolution("0xAAA")
    price_payload = _make_price("0xAAA", yes_ask=0.55)
    s._check_opportunity("0xAAA", res_payload, price_payload)

    assert mock_llm.call_count == 0, "Should have used the loaded disk cache"


# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------

def test_parse_llm_response_direct_json(scorer):
    raw = json.dumps({"probability": 0.88, "reasoning": "Clear condition"})
    prob, reasoning = scorer._parse_llm_response(raw)
    assert abs(prob - 0.88) < 1e-9
    assert reasoning == "Clear condition"


def test_parse_llm_response_embedded_in_prose(scorer):
    raw = 'Based on the analysis: {"probability": 0.91, "reasoning": "Strong"} seems right.'
    prob, reasoning = scorer._parse_llm_response(raw)
    assert abs(prob - 0.91) < 1e-9
    assert reasoning == "Strong"


def test_parse_llm_response_invalid_raises(scorer):
    with pytest.raises(ValueError):
        scorer._parse_llm_response("This is not JSON at all.")


# ---------------------------------------------------------------------------
# Bus / audit integration
# ---------------------------------------------------------------------------

def test_signal_published_to_bus(scorer_and_bus, tmp_path):
    s, bus = scorer_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_resolution(bus, "0xAAA")
    s.run_once()

    # Poll as a fresh consumer to see the published trade:signal
    events = bus.poll("TEST_CHECKER", topics=["trade:signal"])
    assert any(
        e["topic"] == "trade:signal" and e["payload"].get("strategy") == CONSUMER_ID
        for e in events
    )


def test_signal_bus_producer(scorer_and_bus):
    s, bus = scorer_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_resolution(bus, "0xAAA")
    s.run_once()

    events = bus.poll("TEST_CHECKER2", topics=["trade:signal"])
    trade_events = [e for e in events if e["topic"] == "trade:signal"]
    assert len(trade_events) >= 1
    assert trade_events[0]["producer"] == CONSUMER_ID


def test_signal_audit_logged(scorer_and_bus):
    s, bus = scorer_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_resolution(bus, "0xAAA")
    s.run_once()

    audit_dir = os.path.join(s.store.base_path, "audit")
    assert os.path.isdir(audit_dir), "Audit directory not created"
    # Audit files are daily-rotated: audit_YYYY_MM_DD.jsonl
    audit_files = [f for f in os.listdir(audit_dir) if f.startswith("audit_") and f.endswith(".jsonl")]
    assert audit_files, "No audit log file found"
    topics = []
    for fname in audit_files:
        with open(os.path.join(audit_dir, fname)) as f:
            for line in f:
                topics.append(json.loads(line)["topic"])
    assert "trade:signal" in topics


def test_run_once_acks_events(scorer_and_bus):
    s, bus = scorer_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_resolution(bus, "0xAAA")
    s.run_once()

    # Second run_once: events acked → no new events polled → updated_markets empty → no signals.
    # If events were NOT acked, they would be re-polled and trigger a signal again.
    second_signals = s.run_once()
    assert second_signals == []


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

def test_resolution_cache_updated_on_event(scorer_and_bus):
    s, bus = scorer_and_bus
    _publish_resolution(bus, "0xAAA")
    s.run_once()
    assert "0xAAA" in s._resolution_cache


def test_price_cache_updated_on_event(scorer_and_bus):
    s, bus = scorer_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    s.run_once()
    assert "0xAAA" in s._price_cache
    assert s._price_cache["0xAAA"]["yes_ask"] == 0.55


def test_no_signal_without_price_cache(scorer_and_bus):
    s, bus = scorer_and_bus
    # Only publish resolution, no price
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals == []


def test_no_signal_without_resolution_cache(scorer_and_bus):
    s, bus = scorer_and_bus
    # Only publish price, no resolution
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    signals = s.run_once()
    assert signals == []


# ---------------------------------------------------------------------------
# Multi-market independence
# ---------------------------------------------------------------------------

def test_multiple_markets_both_signal(scorer_and_bus):
    s, bus = scorer_and_bus
    # Both markets: high LLM prob (0.92), low ask (0.55) → edge 0.37
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_price(bus, "0xBBB", yes_ask=0.55)
    _publish_resolution(bus, "0xAAA")
    _publish_resolution(bus, "0xBBB")
    signals = s.run_once()
    market_ids = {sig["market_id"] for sig in signals}
    assert "0xAAA" in market_ids
    assert "0xBBB" in market_ids


def test_multiple_markets_only_one_signals(tmp_path):
    import time
    state_path = str(tmp_path / "state")
    mock_llm   = MockLLMClient(probability=0.92)
    s   = PolyOppScorer(base_path=state_path, llm_client=mock_llm)
    bus = PolyEventBus(base_path=state_path)

    now = time.time()
    # Pre-seed LLM cache so probabilities are deterministic regardless of set iteration order
    s._llm_cache["0xAAA"] = {"probability": 0.92, "reasoning": "high", "timestamp": now}
    s._llm_cache["0xBBB"] = {"probability": 0.80, "reasoning": "low",  "timestamp": now}

    _publish_price(bus, "0xAAA", yes_ask=0.55)  # edge = 0.92 - 0.55 = 0.37 → signal
    _publish_price(bus, "0xBBB", yes_ask=0.55)  # prob 0.80 < MIN_LLM_PROBABILITY → no signal
    _publish_resolution(bus, "0xAAA")
    _publish_resolution(bus, "0xBBB")

    signals = s.run_once()
    assert len(signals) == 1
    assert signals[0]["market_id"] == "0xAAA"
