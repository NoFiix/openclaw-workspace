"""
Tests for POLY_COMPOUNDER.

Coverage:
- Trade event collection from audit log (include/exclude by topic)
- No-trade path: zero-lessons envelope, no LLM call
- LLM called with non-empty prompt containing strategy name
- Invalid (non-JSON) LLM response handled gracefully
- All required envelope fields present in output
- trades_analyzed count accurate
- strategies_covered derived from event payloads
- lessons list populated from mock LLM response
- Learnings written to correct file path
- Second run overwrites first file
- run_once() returns dict with trades_analyzed
"""

import datetime
import json
import pytest
from unittest.mock import MagicMock

from core.poly_audit_log import PolyAuditLog
from evaluation.poly_compounder import PolyCompounder, TRADE_TOPICS, LEARNINGS_DIR


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

TEST_DATE     = datetime.date.today().isoformat()
TEST_STRATEGY = "POLY_ARB_SCANNER"

VALID_LLM_RESPONSE = json.dumps({
    "summary": "Strong arb performance today.",
    "lessons": [
        {
            "type": "pattern",
            "strategy": TEST_STRATEGY,
            "insight": "YES+NO spreads < 0.97 produced consistent fills.",
            "confidence": "high",
        }
    ],
})


def _mock_llm(response_text=VALID_LLM_RESPONSE):
    """Return a mock LLM client whose messages.create() returns response_text."""
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    client.messages.create.return_value = msg
    return client


def _write_trade_event(audit: PolyAuditLog, topic: str,
                       strategy: str = TEST_STRATEGY, size_eur: float = 25.0):
    """Write a trade event directly to the audit log."""
    payload = {
        "strategy":  strategy,
        "market_id": "0xabc",
        "direction": "BUY_YES",
        "size_eur":  size_eur,
    }
    if topic == "risk:kill_switch":
        payload = {"strategy": strategy, "action": "pause_strategy", "reason": "daily_drawdown"}
    audit.log_event(topic=topic, producer=strategy, payload=payload)


@pytest.fixture
def compounder(tmp_path):
    """PolyCompounder with injected mock LLM and empty state."""
    return PolyCompounder(base_path=str(tmp_path), llm_client=_mock_llm())


# ---------------------------------------------------------------------------
# Trade collection
# ---------------------------------------------------------------------------

def test_collect_trades_returns_relevant_events(tmp_path):
    c = PolyCompounder(base_path=str(tmp_path), llm_client=_mock_llm())
    _write_trade_event(c.audit, "trade:paper_executed")
    _write_trade_event(c.audit, "trade:live_executed")
    _write_trade_event(c.audit, "risk:kill_switch")
    # irrelevant
    c.audit.log_event("signal:routed", "ROUTER", {"strategy": TEST_STRATEGY, "topic": "execute:paper"})

    result = c._collect_trades()
    assert len(result) == 3
    topics = {e["topic"] for e in result}
    assert topics == {"trade:paper_executed", "trade:live_executed", "risk:kill_switch"}


def test_collect_trades_excludes_irrelevant_topics(tmp_path):
    c = PolyCompounder(base_path=str(tmp_path), llm_client=_mock_llm())
    c.audit.log_event("signal:routed", "ROUTER", {"x": 1})
    c.audit.log_event("registry:status_updated", "REG", {"x": 1})
    c.audit.log_event("account:created", "ACC", {"x": 1})

    result = c._collect_trades()
    assert result == []


# ---------------------------------------------------------------------------
# No-trade path
# ---------------------------------------------------------------------------

def test_run_with_no_trades_returns_zero_analyzed(tmp_path):
    mock_llm = _mock_llm()
    c = PolyCompounder(base_path=str(tmp_path), llm_client=mock_llm)

    learnings = c.run(date_str=TEST_DATE)

    assert learnings["trades_analyzed"] == 0
    assert learnings["lessons"] == []
    assert learnings["strategies_covered"] == []
    # LLM must NOT be called when there are no trades
    mock_llm.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# LLM integration
# ---------------------------------------------------------------------------

def test_llm_called_with_non_empty_prompt(tmp_path):
    mock_llm = _mock_llm()
    c = PolyCompounder(base_path=str(tmp_path), llm_client=mock_llm)
    _write_trade_event(c.audit, "trade:paper_executed")

    c.run(date_str=TEST_DATE)

    mock_llm.messages.create.assert_called_once()
    call_kwargs = mock_llm.messages.create.call_args
    prompt = call_kwargs.kwargs.get("messages", call_kwargs.args[0] if call_kwargs.args else [])[0]["content"]
    assert TEST_STRATEGY in prompt


def test_invalid_llm_json_handled_gracefully(tmp_path):
    mock_llm = _mock_llm(response_text="Not valid JSON at all!")
    c = PolyCompounder(base_path=str(tmp_path), llm_client=mock_llm)
    _write_trade_event(c.audit, "trade:paper_executed")

    learnings = c.run(date_str=TEST_DATE)

    assert isinstance(learnings, dict)
    assert learnings["lessons"] == []
    assert "Not valid JSON" in learnings["summary"]


# ---------------------------------------------------------------------------
# Output correctness
# ---------------------------------------------------------------------------

def test_learnings_contain_required_fields(tmp_path, compounder):
    _write_trade_event(compounder.audit, "trade:paper_executed")
    learnings = compounder.run(date_str=TEST_DATE)

    required = {"date", "generated_at", "trades_analyzed", "strategies_covered", "summary", "lessons"}
    assert required.issubset(learnings.keys())


def test_trades_analyzed_count_accurate(tmp_path, compounder):
    _write_trade_event(compounder.audit, "trade:paper_executed")
    _write_trade_event(compounder.audit, "trade:paper_executed")
    _write_trade_event(compounder.audit, "risk:kill_switch")

    learnings = compounder.run(date_str=TEST_DATE)

    assert learnings["trades_analyzed"] == 3


def test_strategies_covered_derived_from_trades(tmp_path):
    mock_llm = _mock_llm()
    c = PolyCompounder(base_path=str(tmp_path), llm_client=mock_llm)
    _write_trade_event(c.audit, "trade:paper_executed", strategy="POLY_ARB_SCANNER")
    _write_trade_event(c.audit, "trade:live_executed",  strategy="POLY_LATENCY_ARB")

    learnings = c.run(date_str=TEST_DATE)

    assert "POLY_ARB_SCANNER" in learnings["strategies_covered"]
    assert "POLY_LATENCY_ARB" in learnings["strategies_covered"]


def test_lessons_list_populated_from_llm_response(tmp_path, compounder):
    _write_trade_event(compounder.audit, "trade:paper_executed")
    learnings = compounder.run(date_str=TEST_DATE)

    assert len(learnings["lessons"]) == 1
    lesson = learnings["lessons"][0]
    assert lesson["type"] == "pattern"
    assert lesson["strategy"] == TEST_STRATEGY
    assert "confidence" in lesson


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_learnings_saved_to_correct_path(tmp_path, compounder):
    _write_trade_event(compounder.audit, "trade:paper_executed")
    compounder.run(date_str=TEST_DATE)

    expected_path = f"{LEARNINGS_DIR}/polymarket_{TEST_DATE}.json"
    data = compounder.store.read_json(expected_path)
    assert data is not None
    assert data["date"] == TEST_DATE


def test_existing_file_overwritten_on_rerun(tmp_path, compounder):
    _write_trade_event(compounder.audit, "trade:paper_executed")
    first  = compounder.run(date_str=TEST_DATE)
    second = compounder.run(date_str=TEST_DATE)

    # Both runs succeed; the file reflects the latest run
    data = compounder.store.read_json(f"{LEARNINGS_DIR}/polymarket_{TEST_DATE}.json")
    assert data["generated_at"] == second["generated_at"]


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------

def test_run_once_returns_dict(tmp_path, compounder):
    result = compounder.run_once()
    assert isinstance(result, dict)
    assert "trades_analyzed" in result
