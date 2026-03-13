"""
Tests for POLY_STRATEGY_SCOUT.

Coverage:
- Empty candidates → empty evaluated list
- Already-scouted candidate skipped (dedup by name)
- More than MAX_NEW_PER_RUN candidates → exactly MAX_NEW_PER_RUN LLM calls
- Platform-filtered candidate skipped when connector unavailable
- Viable candidate calls LLM once
- Prompt contains candidate description
- Invalid (non-JSON) LLM response handled gracefully
- Viable candidate (score ≥ 40) → flagged_for_human=True, status="pending_human"
- Non-viable candidate (score < 40) → flagged_for_human=False, status="rejected"
- Viable candidate publishes scout:new_strategy_found on bus
- Results persisted to research/scouted_strategies.json
- Stopped strategies returned as reactivation_candidates
"""

import json
import pytest
from unittest.mock import MagicMock

from evaluation.poly_strategy_scout import (
    PolyStrategyScout,
    MAX_NEW_PER_RUN,
    MIN_VIABILITY_SCORE,
    SCOUTED_FILE,
)


# ---------------------------------------------------------------------------
# Mock responses
# ---------------------------------------------------------------------------

VIABLE_RESPONSE = json.dumps({
    "viability_score": 72,
    "verdict":         "VIABLE",
    "confidence":      "medium",
    "summary":         "Strong momentum edge in short-resolution binary markets.",
    "edge_source":     "momentum",
    "risks":           ["liquidity risk", "market saturation"],
    "suggested_parameters": {"lookback_hours": 4, "min_rise_pct": 0.06},
})

NOT_VIABLE_RESPONSE = json.dumps({
    "viability_score": 20,
    "verdict":         "NOT_VIABLE",
    "confidence":      "high",
    "summary":         "Insufficient edge; highly competitive alpha.",
    "edge_source":     "arbitrage",
    "risks":           ["no durable edge"],
    "suggested_parameters": {},
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm(response_json: str = VIABLE_RESPONSE) -> MagicMock:
    """Return a mock LLM client whose messages.create() returns response_json."""
    client = MagicMock()
    msg    = MagicMock()
    msg.content = [MagicMock(text=response_json)]
    client.messages.create.return_value = msg
    return client


def _candidate(name: str = "POLY_MOMENTUM_STRAT", platform: str = "polymarket") -> dict:
    """Return a minimal candidate dict."""
    return {
        "name":                name,
        "description":         f"{name} — momentum-based binary market strategy.",
        "category":            "momentum",
        "platform":            platform,
        "proposed_parameters": {"lookback_hours": 3, "min_rise_pct": 0.05},
    }


def _setup(tmp_path, response_json: str = VIABLE_RESPONSE) -> PolyStrategyScout:
    """Return a PolyStrategyScout with mock LLM and empty state."""
    return PolyStrategyScout(base_path=str(tmp_path), llm_client=_mock_llm(response_json))


# ---------------------------------------------------------------------------
# Guard / dedup
# ---------------------------------------------------------------------------

def test_empty_candidates_returns_empty_evaluated(tmp_path):
    scout = _setup(tmp_path)
    result = scout.run_once(candidates=[])
    assert result["evaluated"] == []
    assert result["flagged_count"] == 0


def test_already_scouted_candidates_skipped(tmp_path):
    scout = _setup(tmp_path)
    # Pre-populate the scouted file with the candidate's name
    existing = {"POLY_MOMENTUM_STRAT": {"name": "POLY_MOMENTUM_STRAT", "viability_score": 50}}
    scout.store.write_json(SCOUTED_FILE, existing)

    result = scout.run_once(candidates=[_candidate("POLY_MOMENTUM_STRAT")])

    assert result["evaluated"] == []
    scout._llm_client.messages.create.assert_not_called()


def test_max_new_per_run_respected(tmp_path):
    scout = _setup(tmp_path)
    candidates = [_candidate(f"POLY_STRAT_{i}") for i in range(MAX_NEW_PER_RUN + 3)]

    result = scout.run_once(candidates=candidates)

    assert len(result["evaluated"]) == MAX_NEW_PER_RUN
    assert scout._llm_client.messages.create.call_count == MAX_NEW_PER_RUN


def test_platform_filtered_when_connector_unavailable(tmp_path):
    scout = _setup(tmp_path)
    kalshi_candidate = _candidate("POLY_KALSHI_ARB", platform="kalshi")

    result = scout.run_once(
        candidates=[kalshi_candidate],
        available_connectors=["polymarket"],
    )

    assert result["evaluated"] == []
    scout._llm_client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# LLM integration
# ---------------------------------------------------------------------------

def test_viable_candidate_calls_llm(tmp_path):
    scout = _setup(tmp_path)
    scout.run_once(candidates=[_candidate()])
    scout._llm_client.messages.create.assert_called_once()


def test_prompt_contains_candidate_description(tmp_path):
    scout = _setup(tmp_path)
    c = _candidate("POLY_MOMENTUM_STRAT")

    scout.run_once(candidates=[c])

    call_kwargs = scout._llm_client.messages.create.call_args
    messages    = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
    prompt      = messages[0]["content"]
    assert c["description"] in prompt


def test_invalid_llm_json_handled_gracefully(tmp_path):
    scout = _setup(tmp_path, response_json="Not valid JSON at all!")

    result = scout.run_once(candidates=[_candidate()])

    assert len(result["evaluated"]) == 1
    entry = result["evaluated"][0]
    assert entry["viability_score"] == 0
    assert entry["verdict"] == "NOT_VIABLE"
    assert "Not valid JSON" in entry["summary"]


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def test_viable_candidate_flagged_for_human(tmp_path):
    scout = _setup(tmp_path, response_json=VIABLE_RESPONSE)

    result = scout.run_once(candidates=[_candidate()])

    entry = result["evaluated"][0]
    assert entry["flagged_for_human"] is True
    assert entry["status"] == "pending_human"
    assert result["flagged_count"] == 1


def test_non_viable_candidate_not_flagged(tmp_path):
    scout = _setup(tmp_path, response_json=NOT_VIABLE_RESPONSE)

    result = scout.run_once(candidates=[_candidate()])

    entry = result["evaluated"][0]
    assert entry["flagged_for_human"] is False
    assert entry["status"] == "rejected"
    assert result["flagged_count"] == 0


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def test_viable_candidate_publishes_bus_event(tmp_path):
    scout = _setup(tmp_path, response_json=VIABLE_RESPONSE)

    scout.run_once(candidates=[_candidate("POLY_MOMENTUM_STRAT")])

    events = scout.bus.poll("TEST_CONSUMER", topics=["scout:new_strategy_found"])
    assert len(events) >= 1
    payload = events[-1]["payload"]
    assert payload["name"] == "POLY_MOMENTUM_STRAT"
    assert payload["viability_score"] == 72


def test_non_viable_no_bus_event(tmp_path):
    scout = _setup(tmp_path, response_json=NOT_VIABLE_RESPONSE)

    scout.run_once(candidates=[_candidate()])

    events = scout.bus.poll("TEST_CONSUMER", topics=["scout:new_strategy_found"])
    assert events == []


def test_results_persisted_to_file(tmp_path):
    scout = _setup(tmp_path, response_json=VIABLE_RESPONSE)

    scout.run_once(candidates=[_candidate("POLY_MOMENTUM_STRAT")])

    data = scout.store.read_json(SCOUTED_FILE)
    assert data is not None
    assert "POLY_MOMENTUM_STRAT" in data
    assert data["POLY_MOMENTUM_STRAT"]["viability_score"] == 72


def test_stopped_strategies_returned_as_reactivation_candidates(tmp_path):
    scout = _setup(tmp_path)

    result = scout.run_once(
        candidates=[],
        stopped_strategies=["POLY_OLD_ARB", "POLY_OLD_SNIPER"],
    )

    assert "POLY_OLD_ARB" in result["reactivation_candidates"]
    assert "POLY_OLD_SNIPER" in result["reactivation_candidates"]
