"""
Tests for POLY_EXECUTION_ROUTER.

Coverage:
- Routing to execute:paper (paper_testing status)
- Routing to execute:live (live status)
- No routing for paused / stopped / awaiting_promotion statuses
- No routing for unknown strategies
- Payload field correctness
- Audit logging on successful route
- run_once integration with bus
- Idempotence (second run_once returns empty list)
"""

import pytest

from core.poly_strategy_registry import PolyStrategyRegistry
from execution.poly_execution_router import PolyExecutionRouter, CONSUMER_ID, STATUS_ROUTE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register(tmp_path, strategy, status):
    """Register a strategy and set its status in the registry."""
    reg = PolyStrategyRegistry(base_path=str(tmp_path))
    reg.register(
        name=strategy,
        category="test",
        platform="polymarket",
        parameters={},
    )
    if status != "scouted":
        reg.update_status(strategy, status)
    return reg


def _make_signal(strategy="POLY_ARB_SCANNER", size_eur=30.0):
    """Build a trade:validated payload dict."""
    return {
        "strategy": strategy,
        "account_id": f"ACC_POLY_{strategy}",
        "market_id": "0xabc123",
        "platform": "polymarket",
        "direction": "BUY_YES",
        "validated_size_eur": size_eur,
        "tranches": [{"size": size_eur, "price_limit": 0.55}],
        "slippage_estimated": 0.003,
    }


@pytest.fixture
def router(tmp_path):
    """Router with POLY_ARB_SCANNER pre-registered at paper_testing status."""
    _register(tmp_path, "POLY_ARB_SCANNER", "paper_testing")
    return PolyExecutionRouter(base_path=str(tmp_path))


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------

def test_paper_testing_routes_to_execute_paper(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "paper_testing")
    r = PolyExecutionRouter(base_path=str(tmp_path))

    result = r.route(_make_signal("POLY_ARB_SCANNER"))

    assert result is not None
    assert result["topic"] == "execute:paper"
    assert result["strategy"] == "POLY_ARB_SCANNER"

    # Verify the event landed on the bus
    events = r.bus.poll("test_consumer", topics=["execute:paper"])
    assert len(events) == 1
    assert events[0]["payload"]["execution_mode"] == "paper"


def test_live_routes_to_execute_live(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "live")
    r = PolyExecutionRouter(base_path=str(tmp_path))

    result = r.route(_make_signal("POLY_ARB_SCANNER"))

    assert result is not None
    assert result["topic"] == "execute:live"

    events = r.bus.poll("test_consumer", topics=["execute:live"])
    assert len(events) == 1
    assert events[0]["payload"]["execution_mode"] == "live"


def test_paused_no_routing(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "paused")
    r = PolyExecutionRouter(base_path=str(tmp_path))

    result = r.route(_make_signal("POLY_ARB_SCANNER"))

    assert result is None
    # No execute event on bus
    paper_events = r.bus.poll("test_consumer", topics=["execute:paper"])
    live_events = r.bus.poll("test_consumer", topics=["execute:live"])
    assert len(paper_events) == 0
    assert len(live_events) == 0


def test_stopped_no_routing(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "stopped")
    r = PolyExecutionRouter(base_path=str(tmp_path))

    result = r.route(_make_signal("POLY_ARB_SCANNER"))

    assert result is None
    assert len(r.bus.poll("test_consumer", topics=["execute:paper"])) == 0
    assert len(r.bus.poll("test_consumer", topics=["execute:live"])) == 0


def test_awaiting_promotion_no_routing(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "awaiting_promotion")
    r = PolyExecutionRouter(base_path=str(tmp_path))

    result = r.route(_make_signal("POLY_ARB_SCANNER"))

    assert result is None
    assert len(r.bus.poll("test_consumer", topics=["execute:paper"])) == 0
    assert len(r.bus.poll("test_consumer", topics=["execute:live"])) == 0


def test_unknown_strategy_no_routing(tmp_path):
    r = PolyExecutionRouter(base_path=str(tmp_path))

    result = r.route(_make_signal("POLY_NONEXISTENT"))

    assert result is None
    assert len(r.bus.poll("test_consumer", topics=["execute:paper"])) == 0
    assert len(r.bus.poll("test_consumer", topics=["execute:live"])) == 0


# ---------------------------------------------------------------------------
# Payload correctness
# ---------------------------------------------------------------------------

def test_execute_paper_payload_fields(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "paper_testing")
    r = PolyExecutionRouter(base_path=str(tmp_path))
    signal = _make_signal("POLY_ARB_SCANNER", size_eur=28.5)

    result = r.route(signal)

    p = result["payload"]
    assert p["execution_mode"] == "paper"
    assert p["strategy"] == "POLY_ARB_SCANNER"
    assert p["account_id"] == "ACC_POLY_POLY_ARB_SCANNER"
    assert p["market_id"] == "0xabc123"
    assert p["platform"] == "polymarket"
    assert p["direction"] == "BUY_YES"
    assert p["size_eur"] == 28.5
    assert p["tranches"] == [{"size": 28.5, "price_limit": 0.55}]
    assert p["slippage_estimated"] == 0.003


def test_execute_live_payload_fields(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "live")
    r = PolyExecutionRouter(base_path=str(tmp_path))

    result = r.route(_make_signal("POLY_ARB_SCANNER"))

    assert result["payload"]["execution_mode"] == "live"


def test_size_eur_mapped_from_validated_size_eur(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "paper_testing")
    r = PolyExecutionRouter(base_path=str(tmp_path))
    signal = _make_signal("POLY_ARB_SCANNER", size_eur=42.0)

    result = r.route(signal)

    assert result["payload"]["size_eur"] == 42.0
    assert "validated_size_eur" not in result["payload"]


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def test_audit_logged_on_successful_route(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "paper_testing")
    r = PolyExecutionRouter(base_path=str(tmp_path))

    r.route(_make_signal("POLY_ARB_SCANNER"))

    events = r.audit.read_events()
    topics = [e["topic"] for e in events]
    assert "signal:routed" in topics

    routed = next(e for e in events if e["topic"] == "signal:routed")
    assert routed["payload"]["strategy"] == "POLY_ARB_SCANNER"
    assert routed["payload"]["topic"] == "execute:paper"


# ---------------------------------------------------------------------------
# run_once / bus integration
# ---------------------------------------------------------------------------

def test_run_once_routes_trade_validated_from_bus(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "paper_testing")
    r = PolyExecutionRouter(base_path=str(tmp_path))

    # Publish a trade:validated event
    r.bus.publish("trade:validated", "POLY_FACTORY_ORCHESTRATOR", _make_signal("POLY_ARB_SCANNER"))

    actions = r.run_once()

    assert len(actions) == 1
    assert actions[0]["topic"] == "execute:paper"
    assert actions[0]["strategy"] == "POLY_ARB_SCANNER"

    # Verify execute:paper event on bus
    execute_events = r.bus.poll("test_consumer", topics=["execute:paper"])
    assert len(execute_events) == 1


def test_run_once_acks_event(tmp_path):
    _register(tmp_path, "POLY_ARB_SCANNER", "paper_testing")
    r = PolyExecutionRouter(base_path=str(tmp_path))

    r.bus.publish("trade:validated", "POLY_FACTORY_ORCHESTRATOR", _make_signal("POLY_ARB_SCANNER"))

    first = r.run_once()
    assert len(first) == 1

    second = r.run_once()
    assert len(second) == 0
