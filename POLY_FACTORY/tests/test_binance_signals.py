"""
Tests for POLY_BINANCE_SIGNALS.
"""

import json
import os
import random
import tempfile
import time

import pytest

from agents.poly_binance_signals import PolyBinanceSignals


def _make_signals(tmp_dir):
    """Create a PolyBinanceSignals instance with a temporary state directory."""
    return PolyBinanceSignals(base_path=tmp_dir)


def _make_binance_payload(symbol="BTCUSDT", price=50000.0, qty=0.1, bids=None, asks=None):
    """Helper to build a minimal Binance feed payload."""
    if bids is None:
        bids = [[49990.0, 1.0], [49980.0, 2.0], [49970.0, 3.0], [49960.0, 1.5], [49950.0, 2.5]]
    if asks is None:
        asks = [[50010.0, 1.0], [50020.0, 2.0], [50030.0, 3.0], [50040.0, 1.5], [50050.0, 2.5]]
    return {
        "symbol": symbol,
        "price": price,
        "last_trade_qty": qty,
        "bids_top5": bids,
        "asks_top5": asks,
    }


# -----------------------------------------------------------------------
# OBI tests
# -----------------------------------------------------------------------

def test_obi_balanced_book(tmp_path):
    sig = _make_signals(str(tmp_path))
    bids = [[100.0, 5.0], [99.0, 5.0]]
    asks = [[101.0, 5.0], [102.0, 5.0]]
    assert sig._compute_obi(bids, asks) == pytest.approx(0.0)


def test_obi_all_bid_pressure(tmp_path):
    sig = _make_signals(str(tmp_path))
    bids = [[100.0, 10.0]]
    asks = [[101.0, 0.0]]
    assert sig._compute_obi(bids, asks) == pytest.approx(1.0)


def test_obi_all_ask_pressure(tmp_path):
    sig = _make_signals(str(tmp_path))
    bids = [[100.0, 0.0]]
    asks = [[101.0, 10.0]]
    assert sig._compute_obi(bids, asks) == pytest.approx(-1.0)


def test_obi_always_in_range(tmp_path):
    sig = _make_signals(str(tmp_path))
    rng = random.Random(42)
    for _ in range(200):
        bids = [[100.0, rng.uniform(0, 100)] for _ in range(5)]
        asks = [[101.0, rng.uniform(0, 100)] for _ in range(5)]
        obi = sig._compute_obi(bids, asks)
        assert -1.0 <= obi <= 1.0


def test_obi_empty_book(tmp_path):
    sig = _make_signals(str(tmp_path))
    assert sig._compute_obi([], []) == pytest.approx(0.0)


# -----------------------------------------------------------------------
# Momentum / EMA tests
# -----------------------------------------------------------------------

def test_ema_seeds_on_first_tick(tmp_path):
    sig = _make_signals(str(tmp_path))
    result = sig._update_ema(None, 50000.0, 0.333)
    assert result == pytest.approx(50000.0)


def test_ema_converges_to_price(tmp_path):
    sig = _make_signals(str(tmp_path))
    ema = None
    for _ in range(100):
        ema = sig._update_ema(ema, 1000.0, 2 / 6)
    assert ema == pytest.approx(1000.0, rel=1e-3)


def test_momentum_zero_during_warmup(tmp_path):
    sig = _make_signals(str(tmp_path))
    for i in range(4):
        sig._tick_count["BTCUSDT"] = i
        momentum = sig._compute_momentum("BTCUSDT", 50000.0 + i * 10)
        assert momentum == pytest.approx(0.0)


def test_momentum_positive_on_uptrend(tmp_path):
    sig = _make_signals(str(tmp_path))
    # Feed 30 rising prices
    for i in range(30):
        sig._tick_count["BTCUSDT"] = sig._tick_count.get("BTCUSDT", 0) + 1
        momentum = sig._compute_momentum("BTCUSDT", 50000.0 + i * 100)
    # After sustained rise, EMA5 > EMA20 → momentum > 0
    assert momentum > 0.0


# -----------------------------------------------------------------------
# CVD tests
# -----------------------------------------------------------------------

def test_cvd_increases_on_price_rise(tmp_path):
    sig = _make_signals(str(tmp_path))
    cvd1 = sig._update_cvd("BTCUSDT", 50000.0, 1.0)
    cvd2 = sig._update_cvd("BTCUSDT", 50100.0, 1.0)  # price up → +1 direction
    assert cvd2 > cvd1


def test_cvd_decreases_on_price_fall(tmp_path):
    sig = _make_signals(str(tmp_path))
    # Seed a previous price
    sig._update_cvd("BTCUSDT", 50000.0, 1.0)
    cvd1 = sig._cvd["BTCUSDT"]
    sig._update_cvd("BTCUSDT", 49900.0, 1.0)  # price down → -1 direction
    cvd2 = sig._cvd["BTCUSDT"]
    assert cvd2 < cvd1


def test_cvd_accumulates_over_ticks(tmp_path):
    sig = _make_signals(str(tmp_path))
    prices = [50000.0, 50100.0, 50200.0, 50300.0]
    for p in prices:
        sig._update_cvd("BTCUSDT", p, 2.0)
    # All rising: CVD should equal 4 * 2.0 = 8.0
    assert sig._cvd["BTCUSDT"] == pytest.approx(8.0)


# -----------------------------------------------------------------------
# VWAP tests
# -----------------------------------------------------------------------

def test_vwap_position_at_vwap(tmp_path):
    sig = _make_signals(str(tmp_path))
    # Feed identical price/qty → VWAP = price → position ≈ 0
    for _ in range(10):
        pos = sig._compute_vwap_position("BTCUSDT", 50000.0, 1.0)
    assert pos == pytest.approx(0.0)


def test_vwap_position_in_range(tmp_path):
    sig = _make_signals(str(tmp_path))
    rng = random.Random(99)
    for _ in range(100):
        price = rng.uniform(45000, 55000)
        qty = rng.uniform(0.01, 10.0)
        pos = sig._compute_vwap_position("BTCUSDT", price, qty)
        assert -1.0 <= pos <= 1.0


# -----------------------------------------------------------------------
# Composite / integration tests
# -----------------------------------------------------------------------

def test_composite_score_in_range(tmp_path):
    sig = _make_signals(str(tmp_path))
    rng = random.Random(7)
    for _ in range(50):
        price = rng.uniform(40000, 60000)
        payload = _make_binance_payload(price=price, qty=rng.uniform(0.01, 5.0))
        result = sig.process_tick(payload)
        assert -1.0 <= result["composite_score"] <= 1.0


def test_build_payload_all_fields(tmp_path):
    sig = _make_signals(str(tmp_path))
    payload = sig._build_payload("BTCUSDT", 50000.0, 0.1, 500.0, 0.2, 0.3)
    required_fields = {"symbol", "price", "obi", "cvd", "vwap_position", "momentum", "composite_score"}
    assert required_fields == set(payload.keys())


def test_process_tick_returns_valid_payload(tmp_path):
    sig = _make_signals(str(tmp_path))
    raw = _make_binance_payload()
    result = sig.process_tick(raw)
    assert result["symbol"] == "BTCUSDT"
    assert result["price"] == pytest.approx(50000.0)
    for field in ("obi", "cvd", "vwap_position", "momentum", "composite_score"):
        assert field in result
        assert isinstance(result[field], float)


def test_update_writes_state_file(tmp_path):
    sig = _make_signals(str(tmp_path))
    raw = _make_binance_payload()
    payload = sig.process_tick(raw)
    sig.update("BTCUSDT", payload)

    state_path = os.path.join(str(tmp_path), "feeds", "binance_signals.json")
    assert os.path.exists(state_path)

    with open(state_path, "r") as f:
        data = json.load(f)
    assert "BTCUSDT" in data


def test_update_publishes_bus_event(tmp_path):
    sig = _make_signals(str(tmp_path))
    raw = _make_binance_payload()
    payload = sig.process_tick(raw)
    sig.update("BTCUSDT", payload)

    # Read the bus pending file and look for our event
    bus_path = os.path.join(str(tmp_path), "bus", "pending_events.jsonl")
    assert os.path.exists(bus_path)

    events = []
    with open(bus_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    matching = [
        e for e in events
        if e.get("topic") == "signal:binance_score"
        and e.get("producer") == "POLY_BINANCE_SIGNALS"
    ]
    assert len(matching) >= 1
    assert matching[-1]["payload"]["symbol"] == "BTCUSDT"


def test_latency_under_50ms(tmp_path):
    sig = _make_signals(str(tmp_path))
    raw = _make_binance_payload()

    # Warm up
    for _ in range(10):
        sig.process_tick(raw)

    n = 1000
    start = time.perf_counter()
    for _ in range(n):
        sig.process_tick(raw)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / n) * 1000
    assert avg_ms < 50.0, f"Average latency {avg_ms:.3f}ms exceeds 50ms limit"
