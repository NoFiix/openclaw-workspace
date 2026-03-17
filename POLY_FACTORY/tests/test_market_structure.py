"""
Tests for POLY_MARKET_STRUCTURE_ANALYZER.
"""

import json
import os
import random

import pytest

from agents.poly_market_structure_analyzer import (
    PolyMarketStructureAnalyzer,
    ILLIQUID_THRESHOLD,
)


def _make_analyzer(tmp_path):
    return PolyMarketStructureAnalyzer(base_path=str(tmp_path))


def _make_price_payload(
    market_id="0xabc",
    volume_24h=1000.0,
    yes_bid=0.48,
    yes_ask=0.52,
    platform="polymarket",
):
    return {
        "market_id": market_id,
        "platform": platform,
        "yes_price": (yes_bid + yes_ask) / 2,
        "no_price": 1 - (yes_bid + yes_ask) / 2,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": 0.48,
        "no_ask": 0.52,
        "volume_24h": volume_24h,
        "data_status": "VALID",
    }


# -----------------------------------------------------------------------
# Spread tests
# -----------------------------------------------------------------------

def test_spread_zero_when_bid_equals_ask(tmp_path):
    az = _make_analyzer(tmp_path)
    assert az._compute_spread_bps(0.50, 0.50) == pytest.approx(0.0)


def test_spread_bps_correct_value(tmp_path):
    az = _make_analyzer(tmp_path)
    # bid=0.49, ask=0.51 → mid=0.50, spread=0.02, bps = 0.02/0.50*10000 = 400
    result = az._compute_spread_bps(0.49, 0.51)
    assert result == pytest.approx(400.0)


def test_spread_always_non_negative(tmp_path):
    az = _make_analyzer(tmp_path)
    rng = random.Random(42)
    for _ in range(200):
        mid = rng.uniform(0.01, 0.99)
        half = rng.uniform(0, mid * 0.4)
        bps = az._compute_spread_bps(mid - half, mid + half)
        assert bps >= 0.0


# -----------------------------------------------------------------------
# Liquidity score tests
# -----------------------------------------------------------------------

def test_liquidity_score_zero_at_low_volume(tmp_path):
    az = _make_analyzer(tmp_path)
    # volume=10: 100*(log10(10)-1)/3 = 100*0/3 = 0
    assert az._compute_liquidity_score(10.0) == pytest.approx(0.0)


def test_liquidity_score_max_at_high_volume(tmp_path):
    az = _make_analyzer(tmp_path)
    # volume=10000: 100*(4-1)/3 = 100
    assert az._compute_liquidity_score(10_000.0) == pytest.approx(100.0)


def test_liquidity_score_in_range(tmp_path):
    az = _make_analyzer(tmp_path)
    for vol in [0.001, 1, 10, 50, 100, 500, 1000, 5000, 10000, 1_000_000]:
        score = az._compute_liquidity_score(vol)
        assert 0.0 <= score <= 100.0


# -----------------------------------------------------------------------
# Executability score tests
# -----------------------------------------------------------------------

def test_executability_low_volume_below_40(tmp_path):
    """Acceptance criterion 1: Market $50 liquidity → score < 40."""
    az = _make_analyzer(tmp_path)
    score = az._compute_executability_score(volume_24h=50.0, spread_bps=0.0)
    assert score < 40.0


def test_executability_high_volume_low_spread_above_70(tmp_path):
    """Acceptance criterion 2: Market $5K, spread 1% → score > 70."""
    az = _make_analyzer(tmp_path)
    # 1% spread on a ~$0.50 market = (0.51-0.49)/0.50 * 10000 = 400 bps
    # But "spread 1%" likely means spread_bps = 100 (1% of price in bps sense)
    score = az._compute_executability_score(volume_24h=5_000.0, spread_bps=100.0)
    assert score > 70.0


def test_executability_spread_penalty(tmp_path):
    az = _make_analyzer(tmp_path)
    score_tight = az._compute_executability_score(1000.0, 0.0)
    score_wide = az._compute_executability_score(1000.0, 200.0)
    assert score_wide < score_tight


def test_executability_in_range(tmp_path):
    az = _make_analyzer(tmp_path)
    rng = random.Random(7)
    for _ in range(200):
        vol = rng.uniform(0, 100_000)
        bps = rng.uniform(0, 2000)
        score = az._compute_executability_score(vol, bps)
        assert 0.0 <= score <= 100.0


# -----------------------------------------------------------------------
# Slippage tests
# -----------------------------------------------------------------------

def test_slippage_1k_positive(tmp_path):
    az = _make_analyzer(tmp_path)
    slippage = az._compute_slippage_1k(spread_bps=100.0, depth_usd=5000.0)
    assert slippage > 0.0


def test_slippage_decreases_with_depth(tmp_path):
    az = _make_analyzer(tmp_path)
    s_shallow = az._compute_slippage_1k(100.0, 500.0)
    s_deep = az._compute_slippage_1k(100.0, 50_000.0)
    assert s_deep < s_shallow


# -----------------------------------------------------------------------
# process_event tests
# -----------------------------------------------------------------------

def test_process_event_all_fields_present(tmp_path):
    az = _make_analyzer(tmp_path)
    payload = _make_price_payload()
    result = az.process_event(payload)
    expected_keys = {
        "market_id", "platform", "spread_bps", "depth_usd",
        "slippage_1k", "liquidity_score", "executability_score",
    }
    assert expected_keys == set(result.keys())


def test_process_event_market_id_and_platform_preserved(tmp_path):
    az = _make_analyzer(tmp_path)
    payload = _make_price_payload(market_id="0xdeadbeef", platform="polymarket")
    result = az.process_event(payload)
    assert result["market_id"] == "0xdeadbeef"
    assert result["platform"] == "polymarket"


# -----------------------------------------------------------------------
# update / integration tests
# -----------------------------------------------------------------------

def test_update_writes_state_file(tmp_path):
    az = _make_analyzer(tmp_path)
    payload = _make_price_payload(market_id="0xaaa", volume_24h=1000.0)
    structure = az.process_event(payload)
    az.update("0xaaa", structure)

    state_path = os.path.join(str(tmp_path), "feeds", "market_structure.json")
    assert os.path.exists(state_path)
    with open(state_path) as f:
        data = json.load(f)
    assert "0xaaa" in data


def test_update_publishes_market_structure_event(tmp_path):
    az = _make_analyzer(tmp_path)
    payload = _make_price_payload(market_id="0xbbb", volume_24h=1000.0)
    structure = az.process_event(payload)
    az.update("0xbbb", structure)

    bus_path = os.path.join(str(tmp_path), "bus", "pending_events.jsonl")
    events = []
    with open(bus_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    matching = [
        e for e in events
        if e.get("topic") == "signal:market_structure"
        and e.get("producer") == "POLY_MARKET_STRUCTURE_ANALYZER"
    ]
    assert len(matching) >= 1
    assert matching[-1]["payload"]["market_id"] == "0xbbb"


def test_update_logs_illiquid_when_score_low(tmp_path):
    """volume=50 → executability < 40 → illiquid logged (no bus publish)."""
    az = _make_analyzer(tmp_path)
    payload = _make_price_payload(market_id="0xccc", volume_24h=50.0, yes_bid=0.50, yes_ask=0.50)
    structure = az.process_event(payload)
    assert structure["executability_score"] < ILLIQUID_THRESHOLD
    az.update("0xccc", structure)

    # Illiquidity info is in state file, no longer published on bus
    state = az.store.read_json("feeds/market_structure.json")
    assert "0xccc" in state
    assert state["0xccc"]["executability_score"] < ILLIQUID_THRESHOLD


def test_update_no_illiquid_when_score_high(tmp_path):
    """volume=5000, tight spread → executability > 70 → not illiquid."""
    az = _make_analyzer(tmp_path)
    payload = _make_price_payload(market_id="0xddd", volume_24h=5_000.0, yes_bid=0.499, yes_ask=0.501)
    structure = az.process_event(payload)
    assert structure["executability_score"] >= ILLIQUID_THRESHOLD
    az.update("0xddd", structure)

    state = az.store.read_json("feeds/market_structure.json")
    assert "0xddd" in state
    assert state["0xddd"]["executability_score"] >= ILLIQUID_THRESHOLD
