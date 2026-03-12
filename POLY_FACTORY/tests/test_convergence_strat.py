"""
Tests for POLY_CONVERGENCE_STRAT — wallet-convergence directional signal strategy.

Coverage:
  - Acceptance criteria (BUY_YES/BUY_NO conditions, all rejection paths)
  - Payload conformance (required fields, values, confidence)
  - Bus / audit integration
  - Cache behaviour (resolution / convergence caches, trigger logic)
  - Multi-market independence
"""

import json
import os

import pytest

from core.poly_event_bus import PolyEventBus
from strategies.poly_convergence_strat import (
    ACCOUNT_ID,
    CONSUMER_ID,
    MAX_AMBIGUITY_SCORE,
    MIN_EV_SCORE,
    MIN_WALLET_COUNT,
    PLATFORM,
    SUGGESTED_SIZE_EUR,
    PolyConvergenceStrat,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_convergence(
    market_id,
    direction="YES",
    wallet_count=3,
    avg_ev_score=0.75,
    convergent_wallets=None,
    detection_timestamp="2026-04-20T14:32:00Z",
):
    if convergent_wallets is None:
        convergent_wallets = [f"0xwallet{i}" for i in range(wallet_count)]
    return {
        "market_id":          market_id,
        "direction":          direction,
        "convergent_wallets": convergent_wallets,
        "wallet_count":       wallet_count,
        "avg_ev_score":       avg_ev_score,
        "detection_timestamp": detection_timestamp,
    }


def _make_resolution(
    market_id,
    boolean_condition="BTC > 100k on 2026-06-01",
    ambiguity_score=2,
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


def _publish_convergence(bus, market_id, **kwargs):
    payload = _make_convergence(market_id, **kwargs)
    bus.publish("signal:wallet_convergence", "POLY_WALLET_TRACKER", payload)


def _publish_resolution(bus, market_id, **kwargs):
    payload = _make_resolution(market_id, **kwargs)
    bus.publish("signal:resolution_parsed", "POLY_MARKET_ANALYST", payload)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def strat_and_bus(tmp_path):
    state_path = str(tmp_path / "state")
    s   = PolyConvergenceStrat(base_path=state_path)
    bus = PolyEventBus(base_path=state_path)
    return s, bus


@pytest.fixture
def strat(tmp_path):
    state_path = str(tmp_path / "state")
    return PolyConvergenceStrat(base_path=state_path)


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------

def test_buy_yes_signal_when_wallets_converge(strat_and_bus):
    """3 wallets, avg_ev=0.75, ambiguity=2, direction=YES → BUY_YES signal."""
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA", direction="YES", wallet_count=3, avg_ev_score=0.75)
    signals = s.run_once()
    assert len(signals) == 1
    assert signals[0]["direction"] == "BUY_YES"


def test_buy_no_signal_when_direction_no(strat_and_bus):
    """direction=NO in convergence payload → BUY_NO signal."""
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA", direction="NO", wallet_count=3, avg_ev_score=0.75)
    signals = s.run_once()
    assert len(signals) == 1
    assert signals[0]["direction"] == "BUY_NO"


def test_no_signal_when_wallet_count_below_min(strat_and_bus):
    """wallet_count=2 < MIN_WALLET_COUNT=3 → no signal."""
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA", wallet_count=MIN_WALLET_COUNT - 1, avg_ev_score=0.75)
    signals = s.run_once()
    assert signals == []


def test_no_signal_when_ev_score_below_min(strat_and_bus):
    """avg_ev_score=0.50 < MIN_EV_SCORE=0.55 → no signal."""
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA", wallet_count=3, avg_ev_score=0.50)
    signals = s.run_once()
    assert signals == []


def test_no_signal_when_ambiguity_too_high(strat_and_bus):
    """ambiguity_score=MAX_AMBIGUITY_SCORE(4) → no signal."""
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA", ambiguity_score=MAX_AMBIGUITY_SCORE)
    _publish_convergence(bus, "0xAAA", wallet_count=3, avg_ev_score=0.75)
    signals = s.run_once()
    assert signals == []


def test_signal_when_ambiguity_just_below_max(strat_and_bus):
    """ambiguity_score=MAX_AMBIGUITY_SCORE-1(3) → signal emitted."""
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA", ambiguity_score=MAX_AMBIGUITY_SCORE - 1)
    _publish_convergence(bus, "0xAAA", wallet_count=3, avg_ev_score=0.75)
    signals = s.run_once()
    assert len(signals) == 1


def test_no_signal_without_resolution_cache(strat_and_bus):
    """Convergence event without resolution cache → no signal."""
    s, bus = strat_and_bus
    _publish_convergence(bus, "0xAAA", wallet_count=3, avg_ev_score=0.75)
    signals = s.run_once()
    assert signals == []


def test_no_signal_without_convergence_cache(strat_and_bus):
    """Resolution event alone does not trigger evaluation → no signal."""
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    signals = s.run_once()
    assert signals == []


# ---------------------------------------------------------------------------
# Payload conformance — top-level fields
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "strategy", "account_id", "market_id", "platform",
    "direction", "confidence", "suggested_size_eur", "signal_type", "signal_detail",
}


def _get_signal(strat_and_bus):
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA", direction="YES", wallet_count=3, avg_ev_score=0.75)
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
    sig = _get_signal(strat_and_bus)
    assert sig["direction"] == "BUY_YES"


def test_signal_payload_direction_buy_no(strat_and_bus):
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA", direction="NO", wallet_count=3, avg_ev_score=0.75)
    signals = s.run_once()
    assert signals[0]["direction"] == "BUY_NO"


def test_signal_payload_signal_type(strat_and_bus):
    sig = _get_signal(strat_and_bus)
    assert sig["signal_type"] == "convergence"


def test_signal_payload_suggested_size_eur(strat_and_bus):
    sig = _get_signal(strat_and_bus)
    assert sig["suggested_size_eur"] == SUGGESTED_SIZE_EUR


def test_signal_confidence_in_range(strat_and_bus):
    sig = _get_signal(strat_and_bus)
    assert 0.0 <= sig["confidence"] <= 1.0


def test_signal_confidence_not_above_1(strat_and_bus):
    """Many wallets with high EV score → confidence clamped at 1.0."""
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA", wallet_count=100, avg_ev_score=0.99)
    signals = s.run_once()
    assert signals[0]["confidence"] <= 1.0


def test_signal_confidence_scales_with_wallet_count(strat_and_bus):
    """More wallets at same EV → higher confidence (before clamping)."""
    s, bus = strat_and_bus

    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA", wallet_count=3, avg_ev_score=0.60)

    _publish_resolution(bus, "0xBBB")
    _publish_convergence(bus, "0xBBB", wallet_count=6, avg_ev_score=0.60)

    signals = s.run_once()
    sig_3 = next(s for s in signals if s["market_id"] == "0xAAA")
    sig_6 = next(s for s in signals if s["market_id"] == "0xBBB")
    assert sig_6["confidence"] > sig_3["confidence"]


# ---------------------------------------------------------------------------
# Signal detail fields and values
# ---------------------------------------------------------------------------

REQUIRED_DETAIL_FIELDS = {
    "boolean_condition", "wallet_count", "avg_ev_score",
    "convergent_wallets", "ambiguity_score", "unexpected_risk_score",
    "detection_timestamp",
}


def test_signal_detail_fields(strat_and_bus):
    sig = _get_signal(strat_and_bus)
    assert REQUIRED_DETAIL_FIELDS.issubset(sig["signal_detail"].keys())


def test_signal_detail_values(strat_and_bus):
    s, bus = strat_and_bus
    COND      = "ETH > 5000 USD on 2026-07-01"
    WALLETS   = ["0xw1", "0xw2", "0xw3"]
    TIMESTAMP = "2026-04-21T10:00:00Z"
    _publish_resolution(bus, "0xAAA", boolean_condition=COND, ambiguity_score=2, unexpected_risk_score=3)
    _publish_convergence(
        bus, "0xAAA",
        direction="YES",
        wallet_count=3,
        avg_ev_score=0.75,
        convergent_wallets=WALLETS,
        detection_timestamp=TIMESTAMP,
    )
    signals = s.run_once()
    detail = signals[0]["signal_detail"]
    assert detail["boolean_condition"] == COND
    assert detail["wallet_count"] == 3
    assert abs(detail["avg_ev_score"] - 0.75) < 1e-9
    assert detail["convergent_wallets"] == WALLETS
    assert detail["ambiguity_score"] == 2
    assert detail["unexpected_risk_score"] == 3
    assert detail["detection_timestamp"] == TIMESTAMP


# ---------------------------------------------------------------------------
# Bus / audit integration
# ---------------------------------------------------------------------------

def test_signal_published_to_bus(strat_and_bus):
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA")
    s.run_once()

    events = bus.poll("TEST_CHECKER", topics=["trade:signal"])
    assert any(
        e["topic"] == "trade:signal" and e["payload"].get("strategy") == CONSUMER_ID
        for e in events
    )


def test_signal_bus_producer(strat_and_bus):
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA")
    s.run_once()

    events = bus.poll("TEST_CHECKER2", topics=["trade:signal"])
    trade_events = [e for e in events if e["topic"] == "trade:signal"]
    assert len(trade_events) >= 1
    assert trade_events[0]["producer"] == CONSUMER_ID


def test_signal_audit_logged(strat_and_bus):
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA")
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
    _publish_resolution(bus, "0xAAA")
    _publish_convergence(bus, "0xAAA")
    s.run_once()

    # Second run_once: events acked → no new events polled → updated_markets empty → no signals.
    second_signals = s.run_once()
    assert second_signals == []


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

def test_resolution_cache_updated_on_event(strat_and_bus):
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    s.run_once()
    assert "0xAAA" in s._resolution_cache
    assert s._resolution_cache["0xAAA"]["boolean_condition"] == "BTC > 100k on 2026-06-01"


def test_convergence_cache_updated_on_event(strat_and_bus):
    s, bus = strat_and_bus
    _publish_convergence(bus, "0xAAA", wallet_count=4, avg_ev_score=0.80)
    s.run_once()
    assert "0xAAA" in s._convergence_cache
    assert s._convergence_cache["0xAAA"]["wallet_count"] == 4
    assert abs(s._convergence_cache["0xAAA"]["avg_ev_score"] - 0.80) < 1e-9


# ---------------------------------------------------------------------------
# Multi-market independence
# ---------------------------------------------------------------------------

def test_multiple_markets_both_signal(strat_and_bus):
    s, bus = strat_and_bus
    _publish_resolution(bus, "0xAAA")
    _publish_resolution(bus, "0xBBB")
    _publish_convergence(bus, "0xAAA", wallet_count=3, avg_ev_score=0.75)
    _publish_convergence(bus, "0xBBB", wallet_count=4, avg_ev_score=0.70)
    signals = s.run_once()
    market_ids = {sig["market_id"] for sig in signals}
    assert "0xAAA" in market_ids
    assert "0xBBB" in market_ids


def test_multiple_markets_only_one_signals(strat_and_bus):
    s, bus = strat_and_bus
    # 0xAAA: 3 wallets, avg_ev=0.75 → signal
    # 0xBBB: 2 wallets (below MIN_WALLET_COUNT) → no signal
    _publish_resolution(bus, "0xAAA")
    _publish_resolution(bus, "0xBBB")
    _publish_convergence(bus, "0xAAA", wallet_count=3, avg_ev_score=0.75)
    _publish_convergence(bus, "0xBBB", wallet_count=2, avg_ev_score=0.75)
    signals = s.run_once()
    assert len(signals) == 1
    assert signals[0]["market_id"] == "0xAAA"
