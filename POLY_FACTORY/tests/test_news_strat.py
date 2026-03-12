"""
Tests for POLY_NEWS_STRAT — news-impact directional signal strategy.

Coverage:
  - Acceptance criteria (BUY_YES/BUY_NO conditions, all rejection paths)
  - Payload conformance (required fields, values, confidence)
  - Signal detail fields
  - Bus / audit integration
  - Cache behaviour (price / news caches, trigger logic)
  - Multi-market independence
"""

import json
import os

import pytest

from core.poly_event_bus import PolyEventBus
from strategies.poly_news_strat import (
    ACCOUNT_ID,
    CONSUMER_ID,
    MAX_NO_ASK,
    MAX_YES_ASK,
    MIN_IMPACT_SCORE,
    PLATFORM,
    SUGGESTED_SIZE_EUR,
    PolyNewsStrat,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_news(
    market_id,
    sentiment="POSITIVE",
    impact_score=0.85,
    headline="Bitcoin ETF approved by SEC",
    source="reuters",
    published_at="2026-04-20T14:32:00Z",
):
    return {
        "market_id":    market_id,
        "headline":     headline,
        "impact_score": impact_score,
        "sentiment":    sentiment,
        "source":       source,
        "published_at": published_at,
    }


def _make_price(market_id, yes_ask=0.55, no_ask=0.45):
    return {
        "market_id": market_id,
        "yes_ask":   yes_ask,
        "no_ask":    no_ask,
    }


def _publish_news(bus, mid, **kwargs):
    payload = _make_news(mid, **kwargs)
    bus.publish("news:high_impact", "OPENCLAW_NEWS_FEED", payload)


def _publish_price(bus, mid, **kwargs):
    payload = _make_price(mid, **kwargs)
    bus.publish("feed:price_update", "POLY_MARKET_CONNECTOR", payload)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def strat_and_bus(tmp_path):
    state_path = str(tmp_path / "state")
    s   = PolyNewsStrat(base_path=state_path)
    bus = PolyEventBus(base_path=state_path)
    return s, bus


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------

def test_buy_yes_signal_on_positive_news(strat_and_bus):
    """POSITIVE, impact=0.85, yes_ask=0.55 → BUY_YES signal."""
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_news(bus, "0xAAA", sentiment="POSITIVE", impact_score=0.85)
    signals = s.run_once()
    assert len(signals) == 1
    assert signals[0]["direction"] == "BUY_YES"


def test_buy_no_signal_on_negative_news(strat_and_bus):
    """NEGATIVE, impact=0.85, no_ask=0.45 → BUY_NO signal."""
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.45)
    _publish_news(bus, "0xAAA", sentiment="NEGATIVE", impact_score=0.85)
    signals = s.run_once()
    assert len(signals) == 1
    assert signals[0]["direction"] == "BUY_NO"


def test_no_signal_when_impact_below_min(strat_and_bus):
    """impact=0.60 < MIN_IMPACT_SCORE=0.70 → no signal."""
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA")
    _publish_news(bus, "0xAAA", impact_score=0.60)
    signals = s.run_once()
    assert signals == []


def test_no_signal_when_sentiment_neutral(strat_and_bus):
    """NEUTRAL sentiment → no signal."""
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA")
    _publish_news(bus, "0xAAA", sentiment="NEUTRAL", impact_score=0.85)
    signals = s.run_once()
    assert signals == []


def test_no_signal_when_yes_ask_too_high(strat_and_bus):
    """POSITIVE, yes_ask=0.85 > MAX_YES_ASK=0.80 → no signal."""
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.85)
    _publish_news(bus, "0xAAA", sentiment="POSITIVE", impact_score=0.85)
    signals = s.run_once()
    assert signals == []


def test_no_signal_when_no_ask_too_high(strat_and_bus):
    """NEGATIVE, no_ask=0.85 > MAX_NO_ASK=0.80 → no signal."""
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA", no_ask=0.85)
    _publish_news(bus, "0xAAA", sentiment="NEGATIVE", impact_score=0.85)
    signals = s.run_once()
    assert signals == []


def test_no_signal_without_price_cache(strat_and_bus):
    """News event only, no price cache → no signal."""
    s, bus = strat_and_bus
    _publish_news(bus, "0xAAA", sentiment="POSITIVE", impact_score=0.85)
    signals = s.run_once()
    assert signals == []


def test_no_signal_without_news_cache(strat_and_bus):
    """Price event alone does not trigger evaluation → no signal."""
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA")
    signals = s.run_once()
    assert signals == []


# ---------------------------------------------------------------------------
# Payload conformance — top-level fields
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "strategy", "account_id", "market_id", "platform",
    "direction", "confidence", "suggested_size_eur", "signal_type", "signal_detail",
}


def _get_signal(strat_and_bus, sentiment="POSITIVE", yes_ask=0.55, no_ask=0.45):
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA", yes_ask=yes_ask, no_ask=no_ask)
    _publish_news(bus, "0xAAA", sentiment=sentiment, impact_score=0.85)
    signals = s.run_once()
    assert signals, "Expected a signal"
    return signals[0]


def test_signal_payload_required_fields(strat_and_bus):
    sig = _get_signal(strat_and_bus)
    assert REQUIRED_FIELDS.issubset(sig.keys())


def test_signal_payload_strategy(strat_and_bus):
    sig = _get_signal(strat_and_bus)
    assert sig["strategy"] == CONSUMER_ID


def test_signal_payload_account_id(strat_and_bus):
    sig = _get_signal(strat_and_bus)
    assert sig["account_id"] == ACCOUNT_ID


def test_signal_payload_platform(strat_and_bus):
    sig = _get_signal(strat_and_bus)
    assert sig["platform"] == PLATFORM


def test_signal_payload_direction_buy_yes(strat_and_bus):
    sig = _get_signal(strat_and_bus, sentiment="POSITIVE")
    assert sig["direction"] == "BUY_YES"


def test_signal_payload_direction_buy_no(strat_and_bus):
    sig = _get_signal(strat_and_bus, sentiment="NEGATIVE")
    assert sig["direction"] == "BUY_NO"


def test_signal_payload_signal_type(strat_and_bus):
    sig = _get_signal(strat_and_bus)
    assert sig["signal_type"] == "news_impact"


def test_signal_payload_suggested_size_eur(strat_and_bus):
    sig = _get_signal(strat_and_bus)
    assert sig["suggested_size_eur"] == SUGGESTED_SIZE_EUR


def test_signal_confidence_equals_impact_score(strat_and_bus):
    """Confidence should equal impact_score (clamped at 1.0)."""
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_news(bus, "0xAAA", sentiment="POSITIVE", impact_score=0.85)
    signals = s.run_once()
    assert abs(signals[0]["confidence"] - 0.85) < 1e-9


def test_signal_confidence_not_above_1(strat_and_bus):
    """impact_score > 1.0 → confidence clamped at 1.0."""
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    # Inject oversized score directly via _check_opportunity
    news  = _make_news("0xAAA", impact_score=1.5)
    price = _make_price("0xAAA", yes_ask=0.55)
    signal = s._check_opportunity("0xAAA", news, price)
    assert signal is not None
    assert signal["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Signal detail fields and values
# ---------------------------------------------------------------------------

REQUIRED_DETAIL_FIELDS_YES = {"headline", "impact_score", "sentiment", "source", "published_at", "yes_ask"}
REQUIRED_DETAIL_FIELDS_NO  = {"headline", "impact_score", "sentiment", "source", "published_at", "no_ask"}


def test_signal_detail_fields_buy_yes(strat_and_bus):
    sig = _get_signal(strat_and_bus, sentiment="POSITIVE")
    assert REQUIRED_DETAIL_FIELDS_YES.issubset(sig["signal_detail"].keys())


def test_signal_detail_fields_buy_no(strat_and_bus):
    sig = _get_signal(strat_and_bus, sentiment="NEGATIVE")
    assert REQUIRED_DETAIL_FIELDS_NO.issubset(sig["signal_detail"].keys())


def test_signal_detail_values(strat_and_bus):
    s, bus = strat_and_bus
    HEADLINE     = "Bitcoin ETF approved by SEC"
    IMPACT       = 0.90
    SOURCE       = "reuters"
    PUBLISHED_AT = "2026-04-20T14:32:00Z"
    YES_ASK      = 0.60

    _publish_price(bus, "0xAAA", yes_ask=YES_ASK)
    _publish_news(
        bus, "0xAAA",
        sentiment="POSITIVE",
        impact_score=IMPACT,
        headline=HEADLINE,
        source=SOURCE,
        published_at=PUBLISHED_AT,
    )
    signals = s.run_once()
    detail = signals[0]["signal_detail"]
    assert detail["headline"]     == HEADLINE
    assert abs(detail["impact_score"] - IMPACT) < 1e-9
    assert detail["sentiment"]    == "POSITIVE"
    assert detail["source"]       == SOURCE
    assert detail["published_at"] == PUBLISHED_AT
    assert abs(detail["yes_ask"]  - YES_ASK) < 1e-9


# ---------------------------------------------------------------------------
# Bus / audit integration
# ---------------------------------------------------------------------------

def test_signal_published_to_bus(strat_and_bus):
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA")
    _publish_news(bus, "0xAAA")
    s.run_once()

    events = bus.poll("TEST_CHECKER", topics=["trade:signal"])
    assert any(
        e["topic"] == "trade:signal" and e["payload"].get("strategy") == CONSUMER_ID
        for e in events
    )


def test_signal_bus_producer(strat_and_bus):
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA")
    _publish_news(bus, "0xAAA")
    s.run_once()

    events = bus.poll("TEST_CHECKER2", topics=["trade:signal"])
    trade_events = [e for e in events if e["topic"] == "trade:signal"]
    assert len(trade_events) >= 1
    assert trade_events[0]["producer"] == CONSUMER_ID


def test_signal_audit_logged(strat_and_bus):
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA")
    _publish_news(bus, "0xAAA")
    s.run_once()

    audit_dir = os.path.join(s.bus.store.base_path, "audit")
    assert os.path.isdir(audit_dir), "Audit directory not created"
    audit_files = [f for f in os.listdir(audit_dir) if f.startswith("audit_") and f.endswith(".jsonl")]
    assert audit_files, "No audit log file found"
    topics = []
    for fname in audit_files:
        with open(os.path.join(audit_dir, fname)) as f:
            for line in f:
                topics.append(json.loads(line)["topic"])
    assert "trade:signal" in topics


def test_run_once_acks_events(strat_and_bus):
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA")
    _publish_news(bus, "0xAAA")
    s.run_once()

    # Second run_once: events acked → no new news events → updated_markets empty → no signals.
    second_signals = s.run_once()
    assert second_signals == []


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

def test_price_cache_updated_on_event(strat_and_bus):
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.62, no_ask=0.38)
    s.run_once()
    assert "0xAAA" in s._price_cache
    assert abs(s._price_cache["0xAAA"]["yes_ask"] - 0.62) < 1e-9


def test_news_cache_updated_on_event(strat_and_bus):
    s, bus = strat_and_bus
    _publish_news(bus, "0xAAA", impact_score=0.77, sentiment="NEGATIVE")
    s.run_once()
    assert "0xAAA" in s._news_cache
    assert abs(s._news_cache["0xAAA"]["impact_score"] - 0.77) < 1e-9
    assert s._news_cache["0xAAA"]["sentiment"] == "NEGATIVE"


# ---------------------------------------------------------------------------
# Multi-market independence
# ---------------------------------------------------------------------------

def test_multiple_markets_both_signal(strat_and_bus):
    s, bus = strat_and_bus
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_price(bus, "0xBBB", no_ask=0.45)
    _publish_news(bus, "0xAAA", sentiment="POSITIVE", impact_score=0.85)
    _publish_news(bus, "0xBBB", sentiment="NEGATIVE", impact_score=0.80)
    signals = s.run_once()
    market_ids = {sig["market_id"] for sig in signals}
    assert "0xAAA" in market_ids
    assert "0xBBB" in market_ids


def test_multiple_markets_only_one_signals(strat_and_bus):
    s, bus = strat_and_bus
    # 0xAAA: POSITIVE, impact=0.85, yes_ask=0.55 → signal
    # 0xBBB: POSITIVE, impact=0.60 < MIN_IMPACT_SCORE → no signal
    _publish_price(bus, "0xAAA", yes_ask=0.55)
    _publish_price(bus, "0xBBB", yes_ask=0.55)
    _publish_news(bus, "0xAAA", sentiment="POSITIVE", impact_score=0.85)
    _publish_news(bus, "0xBBB", sentiment="POSITIVE", impact_score=0.60)
    signals = s.run_once()
    assert len(signals) == 1
    assert signals[0]["market_id"] == "0xAAA"
