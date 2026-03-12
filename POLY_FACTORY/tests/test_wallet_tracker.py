"""
Tests for POLY_WALLET_TRACKER.
"""

import json
import os
import tempfile

import pytest

from agents.poly_wallet_tracker import PolyWalletTracker, CONVERGENCE_THRESHOLD


def _write_rules(tmp_path, rules):
    """Write a blacklist rules JSON file and return its path."""
    path = os.path.join(str(tmp_path), "test_rules.json")
    with open(path, "w") as f:
        json.dump(rules, f)
    return path


def _make_tracker(tmp_path, rules=None):
    """Create a PolyWalletTracker with a temp state dir and optional custom rules."""
    if rules is None:
        rules = {"max_positions": 100, "min_avg_position_size": 5.0}
    rules_path = _write_rules(tmp_path, rules)
    return PolyWalletTracker(base_path=str(tmp_path), rules_path=rules_path)


def _make_wallet_payload(wallet, positions):
    return {"wallet": wallet, "positions": positions, "data_status": "VALID"}


def _pos(market_id, side, size, avg_price):
    return {"market_id": market_id, "side": side, "size": size, "avg_price": avg_price}


# -----------------------------------------------------------------------
# EV score tests
# -----------------------------------------------------------------------

def test_ev_score_high_discount(tmp_path):
    t = _make_tracker(tmp_path)
    positions = [_pos("0xabc", "YES", 100.0, 0.10)]
    assert t._compute_ev_score(positions) == pytest.approx(0.90)


def test_ev_score_at_par(tmp_path):
    t = _make_tracker(tmp_path)
    positions = [_pos("0xabc", "YES", 100.0, 1.0)]
    assert t._compute_ev_score(positions) == pytest.approx(0.0)


def test_ev_score_weighted_by_size(tmp_path):
    t = _make_tracker(tmp_path)
    # 100 units at 0.20 (ev=0.80) + 300 units at 0.60 (ev=0.40)
    # weighted avg = (100*0.80 + 300*0.40) / 400 = (80+120)/400 = 0.50
    positions = [
        _pos("0xabc", "YES", 100.0, 0.20),
        _pos("0xdef", "NO",  300.0, 0.60),
    ]
    assert t._compute_ev_score(positions) == pytest.approx(0.50)


def test_ev_score_empty_positions(tmp_path):
    t = _make_tracker(tmp_path)
    assert t._compute_ev_score([]) == pytest.approx(0.0)


# -----------------------------------------------------------------------
# Specialization tests
# -----------------------------------------------------------------------

def test_specialization_all_yes(tmp_path):
    t = _make_tracker(tmp_path)
    positions = [
        _pos("0xa", "YES", 200.0, 0.40),
        _pos("0xb", "YES", 300.0, 0.35),
    ]
    score, direction = t._compute_specialization(positions)
    assert score == pytest.approx(1.0)
    assert direction == "YES"


def test_specialization_all_no(tmp_path):
    t = _make_tracker(tmp_path)
    positions = [_pos("0xa", "NO", 500.0, 0.30)]
    score, direction = t._compute_specialization(positions)
    assert score == pytest.approx(1.0)
    assert direction == "NO"


def test_specialization_mixed(tmp_path):
    t = _make_tracker(tmp_path)
    positions = [
        _pos("0xa", "YES", 100.0, 0.50),
        _pos("0xb", "NO",  100.0, 0.50),
    ]
    score, direction = t._compute_specialization(positions)
    assert score == pytest.approx(0.5)
    assert direction == "YES"  # YES wins tie


def test_specialization_empty(tmp_path):
    t = _make_tracker(tmp_path)
    score, direction = t._compute_specialization([])
    assert score == pytest.approx(0.0)
    assert direction == "NONE"


# -----------------------------------------------------------------------
# Blacklist tests
# -----------------------------------------------------------------------

def test_blacklist_too_many_positions(tmp_path):
    rules = {"max_positions": 3, "min_avg_position_size": 0.0}
    t = _make_tracker(tmp_path, rules)
    positions = [_pos(f"0x{i}", "YES", 100.0, 0.40) for i in range(4)]
    blacklisted, reason = t._is_blacklisted(positions, rules)
    assert blacklisted is True
    assert reason == "too_many_positions"


def test_blacklist_dust_positions(tmp_path):
    rules = {"max_positions": 100, "min_avg_position_size": 10.0}
    t = _make_tracker(tmp_path, rules)
    positions = [_pos("0xa", "YES", 2.0, 0.40), _pos("0xb", "YES", 3.0, 0.40)]
    blacklisted, reason = t._is_blacklisted(positions, rules)
    assert blacklisted is True
    assert reason == "dust_positions"


def test_blacklist_valid_wallet(tmp_path):
    t = _make_tracker(tmp_path)
    positions = [_pos("0xa", "YES", 500.0, 0.40), _pos("0xb", "NO", 200.0, 0.35)]
    blacklisted, reason = t._is_blacklisted(positions, t.rules)
    assert blacklisted is False
    assert reason is None


# -----------------------------------------------------------------------
# Convergence tests  (key acceptance criteria)
# -----------------------------------------------------------------------

def test_convergence_emits_event_at_3_wallets(tmp_path):
    """3 wallets on same market/direction → convergence event emitted."""
    t = _make_tracker(tmp_path)
    market = "0xmarket1"
    for i in range(3):
        payload = _make_wallet_payload(
            f"0xwallet{i}",
            [_pos(market, "YES", 500.0, 0.30 + i * 0.05)],
        )
        t.process_event(payload)

    bus_path = os.path.join(str(tmp_path), "bus", "pending_events.jsonl")
    events = []
    with open(bus_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    convergence = [
        e for e in events
        if e.get("topic") == "signal:wallet_convergence"
        and e["payload"].get("market_id") == market
        and e["payload"].get("direction") == "YES"
    ]
    assert len(convergence) >= 1


def test_convergence_no_event_below_threshold(tmp_path):
    """Only 2 wallets → no convergence event."""
    t = _make_tracker(tmp_path)
    market = "0xmarket2"
    for i in range(CONVERGENCE_THRESHOLD - 1):
        payload = _make_wallet_payload(
            f"0xwallet{i}",
            [_pos(market, "YES", 500.0, 0.40)],
        )
        t.process_event(payload)

    bus_path = os.path.join(str(tmp_path), "bus", "pending_events.jsonl")
    if not os.path.exists(bus_path):
        return  # no events at all → pass

    events = []
    with open(bus_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    convergence = [
        e for e in events
        if e.get("topic") == "signal:wallet_convergence"
        and e["payload"].get("market_id") == market
    ]
    assert len(convergence) == 0


def test_convergence_excludes_blacklisted(tmp_path):
    """2 clean + 1 blacklisted → total eligible < 3, no event."""
    rules = {"max_positions": 2, "min_avg_position_size": 0.0}
    t = _make_tracker(tmp_path, rules)
    market = "0xmarket3"

    # 2 clean wallets (1 position each, within max_positions=2)
    for i in range(2):
        payload = _make_wallet_payload(
            f"0xclean{i}",
            [_pos(market, "YES", 500.0, 0.30)],
        )
        t.process_event(payload)

    # 1 spam wallet (3 positions > max_positions=2)
    spam_payload = _make_wallet_payload(
        "0xspam",
        [_pos(market, "YES", 100.0, 0.30) for _ in range(3)],
    )
    t.process_event(spam_payload)

    bus_path = os.path.join(str(tmp_path), "bus", "pending_events.jsonl")
    if not os.path.exists(bus_path):
        return

    events = []
    with open(bus_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    convergence = [
        e for e in events
        if e.get("topic") == "signal:wallet_convergence"
        and e["payload"].get("market_id") == market
    ]
    assert len(convergence) == 0


def test_convergence_event_payload_fields(tmp_path):
    """Convergence payload must contain all 6 required fields."""
    t = _make_tracker(tmp_path)
    market = "0xmarket4"
    for i in range(3):
        payload = _make_wallet_payload(
            f"0xw{i}",
            [_pos(market, "YES", 500.0, 0.35)],
        )
        t.process_event(payload)

    bus_path = os.path.join(str(tmp_path), "bus", "pending_events.jsonl")
    events = []
    with open(bus_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    convergence = [e for e in events if e.get("topic") == "signal:wallet_convergence"]
    assert len(convergence) >= 1

    p = convergence[-1]["payload"]
    required = {"market_id", "direction", "convergent_wallets", "wallet_count",
                "avg_ev_score", "detection_timestamp"}
    assert required == set(p.keys())


def test_convergence_avg_ev_score_correct(tmp_path):
    """avg_ev_score must be the mean of per-position EVs across converging wallets."""
    t = _make_tracker(tmp_path)
    market = "0xmarket5"
    prices = [0.30, 0.40, 0.50]  # EVs: 0.70, 0.60, 0.50 → avg = 0.60
    for i, price in enumerate(prices):
        payload = _make_wallet_payload(
            f"0xevw{i}",
            [_pos(market, "YES", 100.0, price)],
        )
        t.process_event(payload)

    bus_path = os.path.join(str(tmp_path), "bus", "pending_events.jsonl")
    events = []
    with open(bus_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    convergence = [
        e for e in events
        if e.get("topic") == "signal:wallet_convergence"
        and e["payload"].get("market_id") == market
    ]
    assert len(convergence) >= 1
    assert convergence[-1]["payload"]["avg_ev_score"] == pytest.approx(0.60, abs=1e-4)


# -----------------------------------------------------------------------
# Integration tests
# -----------------------------------------------------------------------

def test_process_event_returns_signal_dict(tmp_path):
    t = _make_tracker(tmp_path)
    payload = _make_wallet_payload(
        "0xabc",
        [_pos("0xm1", "YES", 500.0, 0.40)],
    )
    signal = t.process_event(payload)
    required = {
        "wallet", "ev_score", "specialization_score", "dominant_direction",
        "position_count", "total_size_usd", "blacklisted", "blacklist_reason",
        "last_updated",
    }
    assert required == set(signal.keys())


def test_update_writes_state_file(tmp_path):
    t = _make_tracker(tmp_path)
    payload = _make_wallet_payload("0xtest", [_pos("0xm1", "YES", 100.0, 0.45)])
    t.process_event(payload)

    state_path = os.path.join(str(tmp_path), "feeds", "wallet_signals.json")
    assert os.path.exists(state_path)
    with open(state_path) as f:
        data = json.load(f)
    assert "0xtest" in data


def test_update_publishes_convergence_on_bus(tmp_path):
    """Convergence event appears on the bus after 3 wallets process the same market."""
    t = _make_tracker(tmp_path)
    market = "0xfinal"
    for i in range(3):
        t.process_event(_make_wallet_payload(
            f"0xfinalw{i}",
            [_pos(market, "YES", 200.0, 0.40)],
        ))

    bus_path = os.path.join(str(tmp_path), "bus", "pending_events.jsonl")
    events = []
    with open(bus_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    convergence = [
        e for e in events
        if e.get("topic") == "signal:wallet_convergence"
        and e.get("producer") == "POLY_WALLET_TRACKER"
        and e["payload"].get("market_id") == market
    ]
    assert len(convergence) >= 1
    assert convergence[-1]["payload"]["wallet_count"] == 3
