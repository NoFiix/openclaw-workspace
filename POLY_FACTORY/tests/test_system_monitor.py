"""
Tests for POLY_SYSTEM_MONITOR — 12 tests covering agent, API, infra checks,
coherence, and run_once bus publishing.
"""

import pytest

from agents.poly_system_monitor import PolySystemMonitor


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def monitor(tmp_path):
    """Return a PolySystemMonitor backed by a tmp state directory."""
    return PolySystemMonitor(base_path=str(tmp_path))


def _agent(name="POLY_TEST", alive=True, last_seen=5, freq=60,
           mem=100, cpu=10, err=0):
    return {
        "name": name,
        "alive": alive,
        "last_seen_seconds": last_seen,
        "expected_freq_s": freq,
        "memory_mb": mem,
        "cpu_pct": cpu,
        "error_rate_per_min": err,
    }


def _api(name="polymarket", connected=True, latency=100, baseline=100):
    return {
        "name": name,
        "connected": connected,
        "latency_ms": latency,
        "baseline_latency_ms": baseline,
    }


def _infra(disk=5.0, ram=50.0, cpu=30.0, db=True):
    return {
        "disk_free_gb": disk,
        "ram_pct": ram,
        "cpu_5min_pct": cpu,
        "db_accessible": db,
    }


# ---------------------------------------------------------------------------
# Agent checks
# ---------------------------------------------------------------------------

def test_agent_down_returns_alert(monitor):
    issues = monitor.check_agents([_agent(alive=False)])
    assert len(issues) == 1
    assert issues[0]["level"] == "ALERT"
    assert "process not running" in issues[0]["issue"]


def test_agent_stale_returns_warning(monitor):
    # last_seen=200 > stale_multiplier(2) * freq(60) = 120
    issues = monitor.check_agents([_agent(last_seen=200, freq=60)])
    assert any(i["issue"] == "stale" and i["level"] == "WARNING" for i in issues)


def test_agent_high_memory_returns_warning(monitor):
    issues = monitor.check_agents([_agent(mem=600)])
    assert any(i["issue"] == "high memory" and i["level"] == "WARNING" for i in issues)


def test_healthy_agent_no_issues(monitor):
    issues = monitor.check_agents([_agent()])
    assert issues == []


# ---------------------------------------------------------------------------
# API checks
# ---------------------------------------------------------------------------

def test_api_down_returns_alert(monitor):
    issues = monitor.check_apis([_api(connected=False)])
    assert len(issues) == 1
    assert issues[0]["level"] == "ALERT"
    assert issues[0]["issue"] == "api down"


def test_api_latency_3x_returns_warning(monitor):
    # latency=310 > 3 * baseline=100 = 300
    issues = monitor.check_apis([_api(latency=310, baseline=100)])
    assert any(i["issue"] == "latency degraded" and i["level"] == "WARNING" for i in issues)


def test_healthy_api_no_issues(monitor):
    issues = monitor.check_apis([_api(latency=80, baseline=100)])
    assert issues == []


# ---------------------------------------------------------------------------
# Infra checks
# ---------------------------------------------------------------------------

def test_infra_low_disk_returns_alert(monitor):
    issues = monitor.check_infra(_infra(disk=0.5))
    assert any(i["issue"] == "low disk space" and i["level"] == "ALERT" for i in issues)


def test_infra_high_ram_returns_alert(monitor):
    issues = monitor.check_infra(_infra(ram=95))
    assert any(i["issue"] == "high RAM usage" and i["level"] == "ALERT" for i in issues)


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------

def test_api_down_publishes_bus_event(monitor):
    monitor.run_once(api_statuses=[_api(connected=False)])
    events = monitor.bus.poll("test_consumer", topics=["system:api_degraded"])
    assert len(events) == 1
    assert events[0]["priority"] == "high"


def test_healthy_run_returns_ok_status(monitor):
    result = monitor.run_once(
        agent_statuses=[_agent()],
        api_statuses=[_api()],
        infra_status=_infra(),
        accounts={},
        registry_entries={},
    )
    assert result["status"] == "OK"


def test_run_once_returns_all_issue_fields(monitor):
    result = monitor.run_once()
    for key in ("agent_issues", "api_issues", "infra_issues", "coherence_issues"):
        assert key in result
    assert "total_issues" in result
    assert "status" in result
    assert "checked_at" in result
