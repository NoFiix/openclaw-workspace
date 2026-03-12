"""
Tests for POLY_PAIR_COST (POLY-030).

Key acceptance criteria:
- (1 - no_bid) - yes_ask > EDGE_THRESHOLD → BUY_YES signal
- (1 - yes_bid) - no_ask > EDGE_THRESHOLD → BUY_NO signal
- Edge ≤ EDGE_THRESHOLD → no signal
- Low executability → no signal
- Payload conforms to trade:signal schema
"""

import pytest
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from strategies.poly_pair_cost import (
    PolyPairCost,
    CONSUMER_ID,
    ACCOUNT_ID,
    EDGE_THRESHOLD,
    MIN_EXECUTABILITY,
    SUGGESTED_SIZE_EUR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MARKET_ID = "0xabc123"


def _publish_market_structure(bus, market_id=MARKET_ID, executability_score=70):
    bus.publish(
        topic="signal:market_structure",
        producer="POLY_MARKET_STRUCTURE_ANALYZER",
        payload={
            "market_id":           market_id,
            "platform":            "polymarket",
            "spread_bps":          200,
            "depth_usd":           50_000.0,
            "slippage_1k":         0.005,
            "liquidity_score":     80,
            "executability_score": executability_score,
        },
    )


def _publish_price_update(
    bus,
    market_id=MARKET_ID,
    yes_ask=0.50,
    yes_bid=0.48,
    no_ask=0.52,
    no_bid=0.50,
):
    bus.publish(
        topic="feed:price_update",
        producer="POLY_MARKET_CONNECTOR",
        payload={
            "market_id":   market_id,
            "platform":    "polymarket",
            "yes_ask":     yes_ask,
            "yes_bid":     yes_bid,
            "no_ask":      no_ask,
            "no_bid":      no_bid,
            "yes_price":   round((yes_ask + yes_bid) / 2, 4),
            "no_price":    round((no_ask + no_bid) / 2, 4),
            "volume_24h":  80_000,
            "data_status": "VALID",
        },
    )


@pytest.fixture
def strategy(tmp_path):
    return PolyPairCost(base_path=str(tmp_path))


@pytest.fixture
def bus(strategy):
    return strategy.bus


# ---------------------------------------------------------------------------
# Ticket acceptance criteria — BUY_YES
# ---------------------------------------------------------------------------

def test_buy_yes_signal_when_yes_edge_exceeds_threshold(strategy, bus):
    """(1 - no_bid) - yes_ask = 0.10 > 0.05 → BUY_YES signal."""
    # no_bid=0.50 → implied fair YES = 0.50; yes_ask=0.40 → edge = 0.10
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert len(signals) == 1
    assert signals[0]["direction"] == "BUY_YES"


def test_no_signal_when_yes_edge_equals_threshold(strategy, bus):
    """edge_yes = EDGE_THRESHOLD exactly → no signal (strict >)."""
    # 1 - 0.50 - 0.45 = 0.05 = EDGE_THRESHOLD
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.45, yes_bid=0.43, no_ask=0.57, no_bid=0.50)
    signals = strategy.run_once()
    assert len(signals) == 0


def test_no_signal_when_yes_edge_below_threshold(strategy, bus):
    """edge_yes < EDGE_THRESHOLD → no signal."""
    # 1 - 0.50 - 0.48 = 0.02 < 0.05
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.48, yes_bid=0.46, no_ask=0.54, no_bid=0.50)
    signals = strategy.run_once()
    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Ticket acceptance criteria — BUY_NO
# ---------------------------------------------------------------------------

def test_buy_no_signal_when_no_edge_exceeds_threshold(strategy, bus):
    """(1 - yes_bid) - no_ask = 0.10 > 0.05 → BUY_NO signal."""
    # yes_bid=0.50 → implied fair NO = 0.50; no_ask=0.40 → edge_no = 0.10
    # Also ensure edge_no > edge_yes so BUY_NO is chosen
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.62, yes_bid=0.50, no_ask=0.40, no_bid=0.38)
    signals = strategy.run_once()
    assert len(signals) == 1
    assert signals[0]["direction"] == "BUY_NO"


def test_no_signal_when_no_edge_equals_threshold(strategy, bus):
    """edge_no = EDGE_THRESHOLD exactly → no signal."""
    # 1 - 0.50 - 0.45 = 0.05 = EDGE_THRESHOLD
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.57, yes_bid=0.50, no_ask=0.45, no_bid=0.43)
    signals = strategy.run_once()
    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Direction selection
# ---------------------------------------------------------------------------

def test_buy_yes_wins_when_yes_edge_larger(strategy):
    """When edge_yes > edge_no, BUY_YES is chosen."""
    strategy._market_structure[MARKET_ID] = {"executability_score": 70}
    # edge_yes = 1 - 0.50 - 0.40 = 0.10 > EDGE_THRESHOLD
    # edge_no  = 1 - 0.38 - 0.60 = 0.02 < EDGE_THRESHOLD
    signal = strategy._check_opportunity(
        MARKET_ID, yes_ask=0.40, yes_bid=0.38, no_ask=0.60, no_bid=0.50
    )
    assert signal is not None
    assert signal["direction"] == "BUY_YES"


def test_buy_no_wins_when_no_edge_larger(strategy):
    """When edge_no > edge_yes, BUY_NO is chosen."""
    strategy._market_structure[MARKET_ID] = {"executability_score": 70}
    # edge_yes = 1 - 0.38 - 0.60 = 0.02 < EDGE_THRESHOLD
    # edge_no  = 1 - 0.50 - 0.40 = 0.10 > EDGE_THRESHOLD
    signal = strategy._check_opportunity(
        MARKET_ID, yes_ask=0.60, yes_bid=0.50, no_ask=0.40, no_bid=0.38
    )
    assert signal is not None
    assert signal["direction"] == "BUY_NO"


def test_buy_yes_preferred_when_edges_equal(strategy):
    """When edge_yes == edge_no (both above threshold), BUY_YES is chosen."""
    strategy._market_structure[MARKET_ID] = {"executability_score": 70}
    # Symmetric: edge_yes = edge_no = 0.10
    signal = strategy._check_opportunity(
        MARKET_ID, yes_ask=0.40, yes_bid=0.40, no_ask=0.40, no_bid=0.50
    )
    # edge_yes = 1 - 0.50 - 0.40 = 0.10; edge_no = 1 - 0.40 - 0.40 = 0.20 → BUY_NO wins
    # Let me use truly equal edges:
    # edge_yes = 1 - 0.50 - 0.40 = 0.10; edge_no = 1 - 0.50 - 0.40 = 0.10
    signal2 = strategy._check_opportunity(
        MARKET_ID, yes_ask=0.40, yes_bid=0.50, no_ask=0.40, no_bid=0.50
    )
    assert signal2 is not None
    assert signal2["direction"] == "BUY_YES"  # yes preferred when equal


def test_no_signal_when_both_edges_below_threshold(strategy):
    """Both edges below threshold → no signal."""
    strategy._market_structure[MARKET_ID] = {"executability_score": 70}
    # edge_yes = 1 - 0.52 - 0.46 = 0.02 < 0.05
    # edge_no  = 1 - 0.46 - 0.52 = 0.02 < 0.05
    signal = strategy._check_opportunity(
        MARKET_ID, yes_ask=0.46, yes_bid=0.44, no_ask=0.52, no_bid=0.50
    )
    assert signal is None


# ---------------------------------------------------------------------------
# Executability filter
# ---------------------------------------------------------------------------

def test_no_signal_when_executability_below_minimum(strategy, bus):
    _publish_market_structure(bus, executability_score=MIN_EXECUTABILITY - 1)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert len(signals) == 0


def test_signal_when_executability_exactly_minimum(strategy, bus):
    _publish_market_structure(bus, executability_score=MIN_EXECUTABILITY)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert len(signals) == 1


def test_no_signal_without_market_structure(strategy, bus):
    """No market_structure cached → executability defaults to 0 → no signal."""
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert len(signals) == 0


def test_no_signal_missing_price_fields(strategy, bus):
    """Price update missing bid/ask fields → no signal."""
    _publish_market_structure(bus)
    bus.publish(
        topic="feed:price_update",
        producer="POLY_MARKET_CONNECTOR",
        payload={"market_id": MARKET_ID, "platform": "polymarket"},
    )
    signals = strategy.run_once()
    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Payload conformance
# ---------------------------------------------------------------------------

def test_signal_payload_required_fields(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    required = {
        "strategy", "account_id", "market_id", "platform",
        "direction", "confidence", "suggested_size_eur",
        "signal_type", "signal_detail",
    }
    assert required.issubset(signals[0].keys())


def test_signal_payload_strategy(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert signals[0]["strategy"] == CONSUMER_ID


def test_signal_payload_account_id(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert signals[0]["account_id"] == ACCOUNT_ID


def test_signal_payload_platform(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert signals[0]["platform"] == "polymarket"


def test_signal_payload_signal_type(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert signals[0]["signal_type"] == "pair_cost"


def test_signal_payload_suggested_size_eur(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert signals[0]["suggested_size_eur"] == SUGGESTED_SIZE_EUR


def test_signal_payload_market_id(strategy, bus):
    _publish_market_structure(bus, market_id="0xdeadbeef")
    _publish_price_update(bus, market_id="0xdeadbeef",
                          yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert signals[0]["market_id"] == "0xdeadbeef"


def test_signal_confidence_in_range(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert 0.0 < signals[0]["confidence"] <= 1.0


def test_signal_confidence_not_above_1(strategy, bus):
    """Very large edge → confidence capped at 1.0."""
    _publish_market_structure(bus)
    # edge_yes = 1 - 0.10 - 0.10 = 0.80 >> threshold
    _publish_price_update(bus, yes_ask=0.10, yes_bid=0.08, no_ask=0.92, no_bid=0.10)
    signals = strategy.run_once()
    assert signals[0]["confidence"] <= 1.0


def test_signal_detail_fields(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    detail = signals[0]["signal_detail"]
    for field in ("yes_ask", "yes_bid", "no_ask", "no_bid", "edge_yes", "edge_no", "edge"):
        assert field in detail


def test_signal_detail_values_buy_yes(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    detail = signals[0]["signal_detail"]
    assert detail["yes_ask"] == 0.40
    assert detail["no_bid"] == 0.50
    expected_edge_yes = round(1.0 - 0.50 - 0.40, 6)
    assert abs(detail["edge_yes"] - expected_edge_yes) < 1e-9
    assert detail["edge"] == detail["edge_yes"]


def test_signal_detail_values_buy_no(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.62, yes_bid=0.50, no_ask=0.40, no_bid=0.38)
    signals = strategy.run_once()
    detail = signals[0]["signal_detail"]
    assert detail["no_ask"] == 0.40
    assert detail["yes_bid"] == 0.50
    expected_edge_no = round(1.0 - 0.50 - 0.40, 6)
    assert abs(detail["edge_no"] - expected_edge_no) < 1e-9
    assert detail["edge"] == detail["edge_no"]


def test_signal_edge_larger_for_better_opportunity(strategy):
    """Larger price gap → larger edge in signal_detail."""
    strategy._market_structure[MARKET_ID] = {"executability_score": 70}
    sig_big   = strategy._check_opportunity(
        MARKET_ID, yes_ask=0.30, yes_bid=0.28, no_ask=0.72, no_bid=0.50
    )  # edge_yes = 0.20
    sig_small = strategy._check_opportunity(
        MARKET_ID, yes_ask=0.42, yes_bid=0.40, no_ask=0.60, no_bid=0.52
    )  # edge_yes = 0.06
    assert sig_big is not None and sig_small is not None
    assert sig_big["signal_detail"]["edge"] > sig_small["signal_detail"]["edge"]


# ---------------------------------------------------------------------------
# Bus and audit integration
# ---------------------------------------------------------------------------

def test_signal_published_to_bus(strategy, bus):
    store = PolyDataStore(base_path=strategy.bus.store.base_path)
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    strategy.run_once()
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "trade:signal" in topics


def test_signal_bus_producer(strategy, bus):
    store = PolyDataStore(base_path=strategy.bus.store.base_path)
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    strategy.run_once()
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "trade:signal")
    assert evt["producer"] == CONSUMER_ID


def test_signal_audit_logged(strategy, bus):
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    strategy.run_once()
    audit = PolyAuditLog(base_path=strategy.bus.store.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "trade:signal" in topics


def test_run_once_acks_events(strategy, bus):
    """After run_once(), a second call returns no new signals."""
    _publish_market_structure(bus)
    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    strategy.run_once()
    signals2 = strategy.run_once()
    assert signals2 == []


# ---------------------------------------------------------------------------
# Market structure caching
# ---------------------------------------------------------------------------

def test_market_structure_cached(strategy, bus):
    _publish_market_structure(bus, executability_score=85)
    strategy.run_once()
    assert MARKET_ID in strategy._market_structure
    assert strategy._market_structure[MARKET_ID]["executability_score"] == 85


def test_cached_structure_enables_signal_on_next_run(strategy, bus):
    """Structure cached in run 1, price update in run 2 → signal on run 2."""
    _publish_market_structure(bus, executability_score=70)
    strategy.run_once()  # caches structure, no price update

    _publish_price_update(bus, yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    signals = strategy.run_once()
    assert len(signals) == 1


# ---------------------------------------------------------------------------
# Multi-market independence
# ---------------------------------------------------------------------------

def test_multiple_markets_only_one_signals(strategy, bus):
    """Two markets: one with edge above threshold, one below → one signal."""
    _publish_market_structure(bus, market_id="0xaaa")
    _publish_market_structure(bus, market_id="0xbbb")
    # 0xaaa: edge_yes = 1 - 0.50 - 0.40 = 0.10 → signal
    _publish_price_update(bus, market_id="0xaaa",
                          yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    # 0xbbb: edge_yes = 1 - 0.50 - 0.47 = 0.03 < 0.05 → no signal
    _publish_price_update(bus, market_id="0xbbb",
                          yes_ask=0.47, yes_bid=0.45, no_ask=0.55, no_bid=0.50)
    signals = strategy.run_once()
    assert len(signals) == 1
    assert signals[0]["market_id"] == "0xaaa"


def test_multiple_markets_both_signal(strategy, bus):
    """Two markets both with edge above threshold → two signals."""
    _publish_market_structure(bus, market_id="0xaaa")
    _publish_market_structure(bus, market_id="0xbbb")
    _publish_price_update(bus, market_id="0xaaa",
                          yes_ask=0.40, yes_bid=0.38, no_ask=0.62, no_bid=0.50)
    _publish_price_update(bus, market_id="0xbbb",
                          yes_ask=0.38, yes_bid=0.36, no_ask=0.64, no_bid=0.50)
    signals = strategy.run_once()
    assert len(signals) == 2
    market_ids = {s["market_id"] for s in signals}
    assert market_ids == {"0xaaa", "0xbbb"}
