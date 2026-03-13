"""
Tests for POLY_STRATEGY_TUNER.

Coverage:
- Guard: < 50 trades → INSUFFICIENT_DATA, no LLM call
- 55 trades → LLM called once
- Prompt includes current registry parameters
- Invalid (non-JSON) LLM response handled gracefully — no exception
- OPTIMIZABLE verdict present in output
- STOP verdict → registry status set to "stopped"
- STOP verdict → account status set to "stopped"
- OPTIMIZABLE verdict → account remains active
- Parameter recommendations have required fields
- Recommendations persisted to evaluation/tuning_recommendations.json
- tuning:recommendation published on bus
- run_once() batch-processes multiple strategies
"""

import json
import pytest
from unittest.mock import MagicMock

from core.poly_strategy_account import PolyStrategyAccount
from core.poly_strategy_registry import PolyStrategyRegistry
from evaluation.poly_performance_logger import PolyPerformanceLogger
from evaluation.poly_strategy_tuner import (
    PolyStrategyTuner,
    MIN_TRADES,
    RECOMMENDATIONS_FILE,
)


# ---------------------------------------------------------------------------
# Constants / mock responses
# ---------------------------------------------------------------------------

TEST_STRATEGY  = "POLY_ARB_SCANNER"
TEST_ACCOUNT   = "ACC_POLY_ARB_SCANNER"

OPTIMIZABLE_RESPONSE = json.dumps({
    "verdict":    "OPTIMIZABLE",
    "confidence": "high",
    "summary":    "Strong performance with slightly elevated slippage.",
    "parameter_recommendations": [
        {
            "parameter":         "edge_threshold",
            "current_value":     0.03,
            "recommended_value": 0.05,
            "rationale":         "Reduces noise trades.",
            "expected_impact":   "medium",
        }
    ],
    "stop_reason": None,
})

STOP_RESPONSE = json.dumps({
    "verdict":    "STOP",
    "confidence": "high",
    "summary":    "Persistent losses indicate structural edge erosion.",
    "parameter_recommendations": [],
    "stop_reason": "Win rate below break-even for 30 consecutive sessions.",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm(response_json: str = OPTIMIZABLE_RESPONSE) -> MagicMock:
    """Return a mock LLM client whose messages.create() returns response_json."""
    client = MagicMock()
    msg    = MagicMock()
    msg.content = [MagicMock(text=response_json)]
    client.messages.create.return_value = msg
    return client


def _setup(tmp_path, n_trades: int = 55, response_json: str = OPTIMIZABLE_RESPONSE):
    """
    Register strategy, create account, log n_trades, return tuner with mock LLM.

    Returns (tuner, registry, account)
    """
    base = str(tmp_path)

    # Register strategy
    registry = PolyStrategyRegistry(base_path=base)
    registry.register(
        name=TEST_STRATEGY,
        category="arbitrage",
        platform="polymarket",
        parameters={"edge_threshold": 0.03, "min_executability": 60},
    )

    # Create account
    account = PolyStrategyAccount.create(
        strategy=TEST_STRATEGY,
        platform="polymarket",
        base_path=base,
    )

    # Log n_trades via PolyPerformanceLogger
    logger = PolyPerformanceLogger(base_path=base, dashboard_path=str(tmp_path / "dash"))
    for i in range(n_trades):
        pnl = 1.0 if i % 3 != 0 else -0.5   # mix of wins/losses
        logger.log_trade(TEST_STRATEGY, pnl=pnl, mode="paper")

    tuner = PolyStrategyTuner(base_path=base, llm_client=_mock_llm(response_json))
    return tuner, registry, account


# ---------------------------------------------------------------------------
# Guard: insufficient trades
# ---------------------------------------------------------------------------

def test_insufficient_trades_returns_early(tmp_path):
    tuner, _, _ = _setup(tmp_path, n_trades=10)
    mock_client = tuner._llm_client

    result = tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["trades_analyzed"] == 10
    assert "reason" in result
    mock_client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# LLM integration
# ---------------------------------------------------------------------------

def test_tune_with_enough_trades_calls_llm(tmp_path):
    tuner, _, _ = _setup(tmp_path, n_trades=55)
    mock_client = tuner._llm_client

    tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    mock_client.messages.create.assert_called_once()


def test_prompt_contains_current_parameters(tmp_path):
    tuner, _, _ = _setup(tmp_path, n_trades=55)
    mock_client = tuner._llm_client

    tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    call_kwargs = mock_client.messages.create.call_args
    messages    = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
    prompt      = messages[0]["content"]
    assert "edge_threshold" in prompt


def test_invalid_llm_json_handled_gracefully(tmp_path):
    tuner, _, _ = _setup(tmp_path, n_trades=55, response_json="Not valid JSON!")

    result = tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    assert isinstance(result, dict)
    assert result["verdict"] == "OPTIMIZABLE"
    assert result["confidence"] == "low"
    assert "Not valid JSON" in result["summary"]


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def test_optimizable_verdict_in_output(tmp_path):
    tuner, _, _ = _setup(tmp_path, n_trades=55, response_json=OPTIMIZABLE_RESPONSE)

    result = tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    assert result["verdict"] == "OPTIMIZABLE"
    assert result["confidence"] == "high"


def test_stop_verdict_updates_registry_to_stopped(tmp_path):
    tuner, registry, _ = _setup(tmp_path, n_trades=55, response_json=STOP_RESPONSE)

    tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    entry = PolyStrategyRegistry(base_path=str(tmp_path)).get(TEST_STRATEGY)
    assert entry["status"] == "stopped"


def test_stop_verdict_updates_account_to_stopped(tmp_path):
    tuner, _, _ = _setup(tmp_path, n_trades=55, response_json=STOP_RESPONSE)

    tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    # Account is archived on stop; load from archive or check in-memory status
    # After archiving the file moves, so we check the audit trail indirectly via
    # the return value instead.
    result = tuner.tune.__func__  # noqa — we rely on the tune() return below

    # Re-create account to verify it was stopped (archived)
    import os
    archive_dir = os.path.join(str(tmp_path), "accounts", "archive")
    archived_files = os.listdir(archive_dir) if os.path.exists(archive_dir) else []
    assert any(TEST_ACCOUNT in f for f in archived_files), (
        f"Expected {TEST_ACCOUNT} in archive, found: {archived_files}"
    )


def test_optimizable_does_not_stop_account(tmp_path):
    tuner, _, _ = _setup(tmp_path, n_trades=55, response_json=OPTIMIZABLE_RESPONSE)

    tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    account = PolyStrategyAccount.load(TEST_ACCOUNT, base_path=str(tmp_path))
    assert account.status != "stopped"


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------

def test_parameter_recommendations_structure(tmp_path):
    tuner, _, _ = _setup(tmp_path, n_trades=55, response_json=OPTIMIZABLE_RESPONSE)

    result = tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    assert len(result["parameter_recommendations"]) == 1
    rec = result["parameter_recommendations"][0]
    for field in ("parameter", "current_value", "recommended_value", "rationale", "expected_impact"):
        assert field in rec, f"Missing field: {field}"


def test_recommendations_saved_to_file(tmp_path):
    tuner, _, _ = _setup(tmp_path, n_trades=55, response_json=OPTIMIZABLE_RESPONSE)

    tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    data = tuner.store.read_json(RECOMMENDATIONS_FILE)
    assert data is not None
    assert TEST_STRATEGY in data
    assert data[TEST_STRATEGY]["verdict"] == "OPTIMIZABLE"


def test_bus_event_published(tmp_path):
    tuner, _, _ = _setup(tmp_path, n_trades=55, response_json=OPTIMIZABLE_RESPONSE)

    tuner.tune(TEST_STRATEGY, TEST_ACCOUNT)

    events = tuner.bus.poll("TEST_CONSUMER", topics=["tuning:recommendation"])
    assert len(events) >= 1
    assert events[-1]["topic"] == "tuning:recommendation"
    assert events[-1]["payload"]["strategy"] == TEST_STRATEGY


# ---------------------------------------------------------------------------
# Batch: run_once
# ---------------------------------------------------------------------------

def test_run_once_batch_processes_strategies(tmp_path):
    base = str(tmp_path)

    # Register and set up two strategies
    registry = PolyStrategyRegistry(base_path=base)
    logger   = PolyPerformanceLogger(
        base_path=base, dashboard_path=str(tmp_path / "dash")
    )

    for strategy in ("POLY_ARB_SCANNER", "POLY_LATENCY_ARB"):
        registry.register(
            name=strategy,
            category="arbitrage",
            platform="polymarket",
            parameters={"edge_threshold": 0.05},
        )
        PolyStrategyAccount.create(
            strategy=strategy,
            platform="polymarket",
            base_path=base,
        )
        for i in range(55):
            logger.log_trade(strategy, pnl=1.0 if i % 2 == 0 else -0.5, mode="paper")

    tuner = PolyStrategyTuner(base_path=base, llm_client=_mock_llm(OPTIMIZABLE_RESPONSE))

    results = tuner.run_once([
        ("POLY_ARB_SCANNER",  "ACC_POLY_ARB_SCANNER"),
        ("POLY_LATENCY_ARB",  "ACC_POLY_LATENCY_ARB"),
    ])

    assert len(results) == 2
    for r in results:
        assert "verdict" in r
        assert r["verdict"] == "OPTIMIZABLE"
