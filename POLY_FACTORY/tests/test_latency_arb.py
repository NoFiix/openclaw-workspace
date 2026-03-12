"""
Tests for POLY_LATENCY_ARB (POLY-028).

Key acceptance criteria from ticket:
- Edge > EDGE_THRESHOLD + confidence >= MIN_CONFIDENCE → signal emitted
- Edge <= EDGE_THRESHOLD → no signal
- Low confidence → no signal
- Payload conforms to trade:signal schema
"""

import pytest
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from strategies.poly_latency_arb import (
    PolyLatencyArb,
    CONSUMER_ID,
    ACCOUNT_ID,
    EDGE_THRESHOLD,
    MIN_CONFIDENCE,
    SUGGESTED_SIZE_EUR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MARKET_ID = "0xabc123"


def _publish_price_update(bus, market_id=MARKET_ID, yes_ask=0.50, no_ask=0.52):
    """Publish a feed:price_update event."""
    bus.publish(
        topic="feed:price_update",
        producer="POLY_MARKET_CONNECTOR",
        payload={
            "market_id":   market_id,
            "platform":    "polymarket",
            "yes_price":   round(yes_ask - 0.01, 4),
            "no_price":    round(no_ask - 0.01, 4),
            "yes_ask":     yes_ask,
            "yes_bid":     round(yes_ask - 0.02, 4),
            "no_ask":      no_ask,
            "no_bid":      round(no_ask - 0.02, 4),
            "volume_24h":  80_000,
            "data_status": "VALID",
        },
    )


def _publish_binance_score(
    bus,
    market_id=MARKET_ID,
    implied_probability=0.75,
    confidence=0.80,
    source_asset="BTC",
    binance_price=45_000.0,
    price_change_pct=2.5,
    symbol=None,
):
    """Publish a signal:binance_score event.

    `symbol` is the overwrite-mode dedup key (OVERWRITE_KEYS["signal:binance_score"]
    = "symbol").  Defaults to source_asset so each unique Binance asset produces an
    independent event.  Pass an explicit value in multi-market tests to ensure each
    market's score survives the overwrite dedup.
    """
    bus.publish(
        topic="signal:binance_score",
        producer="POLY_BINANCE_FEED",
        payload={
            "market_id":           market_id,
            "symbol":              symbol if symbol is not None else source_asset,
            "implied_probability": implied_probability,
            "confidence":          confidence,
            "source_asset":        source_asset,
            "binance_price":       binance_price,
            "price_change_pct":    price_change_pct,
        },
    )


@pytest.fixture
def strategy(tmp_path):
    return PolyLatencyArb(base_path=str(tmp_path))


@pytest.fixture
def bus(strategy):
    return strategy.bus


# ---------------------------------------------------------------------------
# Core signal detection — ticket acceptance criteria
# ---------------------------------------------------------------------------

def test_signal_emitted_when_edge_exceeds_threshold(strategy, bus):
    """implied_prob 0.75 - yes_ask 0.50 = 0.25 > EDGE_THRESHOLD → signal."""
    _publish_price_update(bus, yes_ask=0.50)
    _publish_binance_score(bus, implied_probability=0.75, confidence=0.80)
    signals = strategy.run_once()
    assert len(signals) == 1


def test_no_signal_when_edge_equals_threshold(strategy, bus):
    """edge = EDGE_THRESHOLD exactly → no signal (strict >)."""
    yes_ask = 0.65
    implied = yes_ask + EDGE_THRESHOLD  # edge = exactly EDGE_THRESHOLD
    _publish_price_update(bus, yes_ask=yes_ask)
    _publish_binance_score(bus, implied_probability=implied, confidence=0.80)
    signals = strategy.run_once()
    assert len(signals) == 0


def test_no_signal_when_edge_below_threshold(strategy, bus):
    """edge < EDGE_THRESHOLD → no signal."""
    _publish_price_update(bus, yes_ask=0.60)
    _publish_binance_score(bus, implied_probability=0.65, confidence=0.80)
    # edge = 0.65 - 0.60 = 0.05 < 0.10
    signals = strategy.run_once()
    assert len(signals) == 0


def test_no_signal_when_confidence_below_minimum(strategy, bus):
    """Large edge but confidence < MIN_CONFIDENCE → no signal."""
    _publish_price_update(bus, yes_ask=0.50)
    _publish_binance_score(
        bus, implied_probability=0.80, confidence=MIN_CONFIDENCE - 0.01
    )
    signals = strategy.run_once()
    assert len(signals) == 0


def test_signal_when_confidence_exactly_minimum(strategy, bus):
    """confidence = MIN_CONFIDENCE exactly → signal allowed."""
    _publish_price_update(bus, yes_ask=0.50)
    _publish_binance_score(
        bus, implied_probability=0.75, confidence=MIN_CONFIDENCE
    )
    signals = strategy.run_once()
    assert len(signals) == 1


def test_no_signal_without_price_data(strategy, bus):
    """No price_update cached → price_cache miss → no signal."""
    _publish_binance_score(bus, implied_probability=0.80, confidence=0.85)
    signals = strategy.run_once()
    assert len(signals) == 0


# ---------------------------------------------------------------------------
# BUY_YES vs BUY_NO direction
# ---------------------------------------------------------------------------

def test_buy_yes_when_yes_edge_is_larger(strategy, bus):
    """implied_prob > yes_ask + EDGE_THRESHOLD → BUY_YES."""
    _publish_price_update(bus, yes_ask=0.50, no_ask=0.52)
    _publish_binance_score(bus, implied_probability=0.75, confidence=0.80)
    signals = strategy.run_once()
    assert signals[0]["direction"] == "BUY_YES"


def test_buy_no_when_no_edge_is_larger(strategy, bus):
    """(1 - implied_prob) > no_ask + EDGE_THRESHOLD → BUY_NO."""
    # implied_prob = 0.20 → NO probability = 0.80; no_ask = 0.55
    # edge_yes = 0.20 - 0.70 = -0.50 (no)
    # edge_no  = 0.80 - 0.55 = 0.25  > 0.10 → BUY_NO
    _publish_price_update(bus, yes_ask=0.70, no_ask=0.55)
    _publish_binance_score(bus, implied_probability=0.20, confidence=0.80)
    signals = strategy.run_once()
    assert len(signals) == 1
    assert signals[0]["direction"] == "BUY_NO"


def test_buy_yes_takes_priority_when_both_edges_above_threshold(strategy, bus):
    """If both YES and NO edges exceed threshold, BUY_YES is chosen first."""
    # Unusual market: very cheap asks on both sides
    # yes_ask = 0.20, no_ask = 0.20, implied_prob = 0.50
    # edge_yes = 0.50 - 0.20 = 0.30 > 0.10
    # edge_no  = 0.50 - 0.20 = 0.30 > 0.10
    _publish_price_update(bus, yes_ask=0.20, no_ask=0.20)
    _publish_binance_score(bus, implied_probability=0.50, confidence=0.80)
    signals = strategy.run_once()
    assert len(signals) == 1
    assert signals[0]["direction"] == "BUY_YES"


# ---------------------------------------------------------------------------
# Payload conformance
# ---------------------------------------------------------------------------

def test_signal_payload_required_fields(strategy, bus):
    """All required trade:signal fields must be present."""
    _publish_price_update(bus, yes_ask=0.50)
    _publish_binance_score(bus, implied_probability=0.75, confidence=0.80)
    signals = strategy.run_once()
    required = {
        "strategy", "account_id", "market_id", "platform",
        "direction", "confidence", "suggested_size_eur",
        "signal_type", "signal_detail",
    }
    assert required.issubset(signals[0].keys())


def test_signal_payload_strategy(strategy, bus):
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75)
    signals = strategy.run_once()
    assert signals[0]["strategy"] == CONSUMER_ID


def test_signal_payload_account_id(strategy, bus):
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75)
    signals = strategy.run_once()
    assert signals[0]["account_id"] == ACCOUNT_ID


def test_signal_payload_platform(strategy, bus):
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75)
    signals = strategy.run_once()
    assert signals[0]["platform"] == "polymarket"


def test_signal_payload_signal_type(strategy, bus):
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75)
    signals = strategy.run_once()
    assert signals[0]["signal_type"] == "latency_arb"


def test_signal_payload_suggested_size_eur(strategy, bus):
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75)
    signals = strategy.run_once()
    assert signals[0]["suggested_size_eur"] == SUGGESTED_SIZE_EUR


def test_signal_payload_market_id(strategy, bus):
    _publish_price_update(bus, market_id="0xdeadbeef")
    _publish_binance_score(bus, market_id="0xdeadbeef", implied_probability=0.75)
    signals = strategy.run_once()
    assert signals[0]["market_id"] == "0xdeadbeef"


def test_signal_confidence_in_range(strategy, bus):
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75, confidence=0.85)
    signals = strategy.run_once()
    assert 0.0 < signals[0]["confidence"] <= 1.0


def test_signal_confidence_not_above_1(strategy, bus):
    """confidence capped at 1.0 even if source confidence > 1."""
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75, confidence=1.5)
    signals = strategy.run_once()
    assert signals[0]["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# signal_detail
# ---------------------------------------------------------------------------

def test_signal_detail_fields(strategy, bus):
    """signal_detail must contain the required sub-fields."""
    _publish_price_update(bus, yes_ask=0.50)
    _publish_binance_score(bus, implied_probability=0.75, confidence=0.80)
    signals = strategy.run_once()
    detail = signals[0]["signal_detail"]
    for field in ("implied_probability", "ask_used", "edge",
                  "direction", "source_asset", "binance_price", "confidence"):
        assert field in detail


def test_signal_detail_edge_correct_buy_yes(strategy, bus):
    """edge = implied_prob - yes_ask for BUY_YES."""
    _publish_price_update(bus, yes_ask=0.50)
    _publish_binance_score(bus, implied_probability=0.75, confidence=0.80)
    signals = strategy.run_once()
    detail = signals[0]["signal_detail"]
    assert abs(detail["edge"] - (0.75 - 0.50)) < 1e-9


def test_signal_detail_edge_correct_buy_no(strategy, bus):
    """edge = (1 - implied_prob) - no_ask for BUY_NO."""
    _publish_price_update(bus, yes_ask=0.70, no_ask=0.55)
    _publish_binance_score(bus, implied_probability=0.20, confidence=0.80)
    signals = strategy.run_once()
    detail = signals[0]["signal_detail"]
    assert abs(detail["edge"] - (0.80 - 0.55)) < 1e-9


def test_signal_detail_source_asset_preserved(strategy, bus):
    """source_asset from Binance score is propagated to signal_detail."""
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75, source_asset="ETH")
    signals = strategy.run_once()
    assert signals[0]["signal_detail"]["source_asset"] == "ETH"


def test_signal_detail_binance_price_preserved(strategy, bus):
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75, binance_price=47_500.0)
    signals = strategy.run_once()
    assert signals[0]["signal_detail"]["binance_price"] == 47_500.0


# ---------------------------------------------------------------------------
# Bus and audit integration
# ---------------------------------------------------------------------------

def test_signal_published_to_bus(strategy, bus):
    """trade:signal must appear in pending_events.jsonl."""
    store = PolyDataStore(base_path=strategy.bus.store.base_path)
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75, confidence=0.80)
    strategy.run_once()
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "trade:signal" in topics


def test_signal_bus_producer(strategy, bus):
    store = PolyDataStore(base_path=strategy.bus.store.base_path)
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75)
    strategy.run_once()
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "trade:signal")
    assert evt["producer"] == CONSUMER_ID


def test_signal_audit_logged(strategy, bus):
    """trade:signal must appear in today's audit log."""
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75, confidence=0.80)
    strategy.run_once()
    audit = PolyAuditLog(base_path=strategy.bus.store.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "trade:signal" in topics


def test_run_once_acks_events(strategy, bus):
    """After run_once(), a second call returns no new signals."""
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.75, confidence=0.80)
    strategy.run_once()
    signals2 = strategy.run_once()
    assert signals2 == []


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------

def test_price_cache_populated_after_run_once(strategy, bus):
    """feed:price_update populates the price cache."""
    _publish_price_update(bus, yes_ask=0.55)
    strategy.run_once()
    assert MARKET_ID in strategy._price_cache
    assert strategy._price_cache[MARKET_ID]["yes_ask"] == 0.55


def test_binance_score_cached_after_run_once(strategy, bus):
    """signal:binance_score populates the binance_scores cache."""
    _publish_price_update(bus)
    _publish_binance_score(bus, implied_probability=0.65, confidence=0.60)
    strategy.run_once()
    assert MARKET_ID in strategy._binance_scores


def test_cached_price_enables_signal_on_next_run(strategy, bus):
    """Price cached in run 1, Binance score in run 2 → signal on run 2."""
    _publish_price_update(bus, yes_ask=0.50)
    strategy.run_once()  # caches price, no binance score yet

    _publish_binance_score(bus, implied_probability=0.75, confidence=0.80)
    signals = strategy.run_once()
    assert len(signals) == 1


def test_price_cache_updated_by_newer_event(strategy, bus):
    """Second price_update for same market_id overwrites the cache."""
    _publish_price_update(bus, yes_ask=0.50)
    _publish_price_update(bus, yes_ask=0.60)
    strategy.run_once()
    assert strategy._price_cache[MARKET_ID]["yes_ask"] == 0.60


# ---------------------------------------------------------------------------
# Multi-market independence
# ---------------------------------------------------------------------------

def test_multiple_markets_only_one_signals(strategy, bus):
    """Two markets: one above EDGE_THRESHOLD, one below → one signal.

    Different `symbol` values (BTC vs ETH) ensure both scores survive the
    overwrite-mode dedup in the event bus (OVERWRITE_KEYS["signal:binance_score"]
    = "symbol").
    """
    _publish_price_update(bus, market_id="0xaaa", yes_ask=0.50)
    _publish_price_update(bus, market_id="0xbbb", yes_ask=0.68)
    # Market 0xaaa: edge = 0.75 - 0.50 = 0.25 → signal
    _publish_binance_score(bus, market_id="0xaaa", implied_probability=0.75,
                           confidence=0.80, symbol="BTC")
    # Market 0xbbb: edge = 0.75 - 0.68 = 0.07 < 0.10 → no signal
    _publish_binance_score(bus, market_id="0xbbb", implied_probability=0.75,
                           confidence=0.80, symbol="ETH")
    signals = strategy.run_once()
    assert len(signals) == 1
    assert signals[0]["market_id"] == "0xaaa"


def test_multiple_markets_both_signal(strategy, bus):
    """Two markets both above EDGE_THRESHOLD → two signals."""
    _publish_price_update(bus, market_id="0xaaa", yes_ask=0.50)
    _publish_price_update(bus, market_id="0xbbb", yes_ask=0.45)
    _publish_binance_score(bus, market_id="0xaaa", implied_probability=0.75,
                           confidence=0.80, symbol="BTC")
    _publish_binance_score(bus, market_id="0xbbb", implied_probability=0.70,
                           confidence=0.80, symbol="ETH")
    signals = strategy.run_once()
    assert len(signals) == 2
    market_ids = {s["market_id"] for s in signals}
    assert market_ids == {"0xaaa", "0xbbb"}


def test_market_scores_are_independent(strategy, bus):
    """Score for market A does not trigger a signal for market B."""
    _publish_price_update(bus, market_id="0xaaa", yes_ask=0.50)
    # Only market B gets a Binance score; market A has no score
    _publish_binance_score(bus, market_id="0xbbb", implied_probability=0.90, confidence=0.90)
    signals = strategy.run_once()
    assert len(signals) == 0  # 0xbbb has no price data in cache


# ---------------------------------------------------------------------------
# _check_opportunity — pure function tests
# ---------------------------------------------------------------------------

def test_check_opportunity_returns_none_without_implied_prob(strategy):
    score = {"confidence": 0.80}
    price = {"yes_ask": 0.50, "no_ask": 0.52}
    assert strategy._check_opportunity("0xtest", score, price) is None


def test_check_opportunity_returns_none_without_price_data(strategy):
    score = {"implied_probability": 0.75, "confidence": 0.80}
    price = {}
    assert strategy._check_opportunity("0xtest", score, price) is None


def test_check_opportunity_returns_dict_on_edge(strategy):
    score = {"implied_probability": 0.75, "confidence": 0.80, "source_asset": "BTC", "binance_price": 45000.0}
    price = {"yes_ask": 0.50, "no_ask": 0.52}
    result = strategy._check_opportunity("0xtest", score, price)
    assert isinstance(result, dict)


def test_check_opportunity_edge_grows_with_price_gap(strategy):
    """Larger gap → higher edge in signal_detail."""
    score_hi = {"implied_probability": 0.90, "confidence": 0.80, "source_asset": "BTC", "binance_price": 45000.0}
    score_lo = {"implied_probability": 0.70, "confidence": 0.80, "source_asset": "BTC", "binance_price": 45000.0}
    price    = {"yes_ask": 0.50, "no_ask": 0.52}

    sig_hi = strategy._check_opportunity("0xtest", score_hi, price)
    sig_lo = strategy._check_opportunity("0xtest", score_lo, price)

    assert sig_hi is not None and sig_lo is not None
    assert sig_hi["signal_detail"]["edge"] > sig_lo["signal_detail"]["edge"]
