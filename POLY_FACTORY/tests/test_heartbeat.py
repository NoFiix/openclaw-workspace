"""
Tests for POLY_HEARTBEAT — 12 tests covering registration, ping,
staleness detection, restart logic, and disable-after-max-restarts.
"""

from datetime import datetime, timedelta, timezone

import pytest

from agents.poly_heartbeat import MAX_RESTARTS, PolyHeartbeat


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hb(tmp_path):
    """PolyHeartbeat with no restart_fn (no-op restarts)."""
    return PolyHeartbeat(base_path=str(tmp_path))


@pytest.fixture
def hb_with_restart(tmp_path):
    """PolyHeartbeat with a spy restart_fn."""
    calls = []

    def _restart(agent_name):
        calls.append(agent_name)
        return True

    instance = PolyHeartbeat(base_path=str(tmp_path), restart_fn=_restart)
    instance._restart_calls = calls
    return instance


# ---------------------------------------------------------------------------
# Helper: backdate an agent's last_seen
# ---------------------------------------------------------------------------

def _backdate(hb, agent_name, seconds_ago):
    """Manually set last_seen to N seconds in the past."""
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    ts = dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
    hb._state["agents"][agent_name]["last_seen"] = ts
    hb._save_state()


# ---------------------------------------------------------------------------
# Registration & ping
# ---------------------------------------------------------------------------

def test_register_adds_agent(hb):
    hb.register("POLY_TEST", expected_freq_s=120.0)
    agent = hb._state["agents"]["POLY_TEST"]
    assert agent["status"] == "active"
    assert agent["restart_count"] == 0
    assert agent["last_seen"] is None
    assert agent["expected_freq_s"] == 120.0


def test_ping_updates_last_seen(hb):
    hb.ping("POLY_TEST")
    last_seen = hb._state["agents"]["POLY_TEST"]["last_seen"]
    assert last_seen is not None
    # Should be a recent timestamp
    dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
    elapsed = (datetime.now(timezone.utc) - dt).total_seconds()
    assert elapsed < 5


def test_ping_publishes_heartbeat_event(hb):
    hb.ping("POLY_TEST")
    events = hb.bus.poll("test_consumer", topics=["system:heartbeat"])
    assert len(events) == 1
    assert events[0]["payload"]["agent"] == "POLY_TEST"


def test_ping_auto_registers_unknown_agent(hb):
    assert "POLY_UNKNOWN" not in hb._state["agents"]
    hb.ping("POLY_UNKNOWN")
    assert "POLY_UNKNOWN" in hb._state["agents"]


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------

def test_check_stale_fresh_agent_not_stale(hb):
    hb.ping("POLY_FRESH")
    stale = hb.check_stale()
    assert all(e["agent"] != "POLY_FRESH" for e in stale)


def test_check_stale_overdue_agent_detected(hb):
    # freq=60, stale_multiplier=2 → stale after 120s; set last_seen to 200s ago
    hb.register("POLY_SLOW", expected_freq_s=60.0)
    _backdate(hb, "POLY_SLOW", seconds_ago=200)
    stale = hb.check_stale()
    assert any(e["agent"] == "POLY_SLOW" for e in stale)


def test_check_stale_never_seen_agent_is_stale(hb):
    hb.register("POLY_SILENT")
    # last_seen is None — never pinged
    stale = hb.check_stale()
    assert any(e["agent"] == "POLY_SILENT" for e in stale)


def test_disabled_agent_skipped_in_check_stale(hb):
    hb.register("POLY_DEAD")
    hb._state["agents"]["POLY_DEAD"]["status"] = "disabled"
    hb._save_state()
    stale = hb.check_stale()
    assert all(e["agent"] != "POLY_DEAD" for e in stale)


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------

def test_run_once_stale_publishes_agent_stale_event(hb):
    hb.register("POLY_STALE")
    # Never pinged → stale
    hb.run_once()
    events = hb.bus.poll("test_consumer", topics=["system:agent_stale"])
    assert len(events) == 1
    assert events[0]["priority"] == "high"
    assert events[0]["payload"]["agent"] == "POLY_STALE"


def test_run_once_calls_restart_fn(hb_with_restart):
    hb_with_restart.register("POLY_CRASHED")
    # Never pinged → stale on first run_once
    hb_with_restart.run_once()
    assert "POLY_CRASHED" in hb_with_restart._restart_calls


def test_run_once_disables_after_max_restarts(hb):
    hb.register("POLY_FLAKY")
    # Run MAX_RESTARTS times without agent ever pinging
    for _ in range(MAX_RESTARTS):
        hb.run_once()

    agent = hb._state["agents"]["POLY_FLAKY"]
    assert agent["status"] == "disabled"
    assert agent["restart_count"] >= MAX_RESTARTS

    # system:agent_disabled must have been published
    events = hb.bus.poll("test_consumer", topics=["system:agent_disabled"])
    assert any(e["payload"]["agent"] == "POLY_FLAKY" for e in events)


def test_run_once_healthy_returns_empty_stale(hb):
    hb.ping("POLY_HEALTHY")
    result = hb.run_once()
    assert result["stale_agents"] == []
    assert result["disabled"] == []
    assert "checked_at" in result
    assert "total_agents" in result
