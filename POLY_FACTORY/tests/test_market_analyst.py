"""
Tests for POLY_MARKET_ANALYST.
All LLM calls are mocked — no real Anthropic API calls are made.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from agents.poly_market_analyst import PolyMarketAnalyst


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_llm_client(response_text):
    """Return a mock Anthropic client that always returns response_text."""
    mock_content = MagicMock()
    mock_content.text = response_text

    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


def _write_prompt(tmp_path):
    """Write a minimal prompt template to tmp_path and return its path."""
    prompts_dir = os.path.join(str(tmp_path), "prompts")
    os.makedirs(prompts_dir, exist_ok=True)
    path = os.path.join(prompts_dir, "resolution_parser_prompt.txt")
    with open(path, "w") as f:
        f.write("Question: {question}\nDescription: {description}\nReturn JSON.")
    return path


def _make_analyst(tmp_path, llm_response=None, llm_client=None):
    """Create a PolyMarketAnalyst with temp state dir and mocked LLM."""
    prompt_path = _write_prompt(tmp_path)
    if llm_client is None and llm_response is not None:
        llm_client = _make_llm_client(llm_response)
    return PolyMarketAnalyst(
        base_path=str(tmp_path),
        prompt_path=prompt_path,
        llm_client=llm_client,
    )


def _json_response(boolean_condition="BTC > 100K", ambiguity=1, risk=1):
    return json.dumps({
        "boolean_condition": boolean_condition,
        "ambiguity_score": ambiguity,
        "unexpected_risk_score": risk,
    })


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

def test_cache_hit_no_second_llm_call(tmp_path):
    """Analyzing the same market_id twice must call LLM only once."""
    client = _make_llm_client(_json_response())
    analyst = _make_analyst(tmp_path, llm_client=client)

    analyst.analyze("0xbtc", "Will BTC reach $100K?", "Resolves YES if BTC...")
    analyst.analyze("0xbtc", "Will BTC reach $100K?", "Resolves YES if BTC...")

    assert client.messages.create.call_count == 1


def test_cache_hit_returns_same_result(tmp_path):
    """Both calls must return identical dicts."""
    analyst = _make_analyst(tmp_path, llm_response=_json_response("BTC > 100K", 1, 1))

    r1 = analyst.analyze("0xbtc", "Q", "D")
    r2 = analyst.analyze("0xbtc", "Q", "D")

    assert r1 == r2


def test_cache_persists_to_state_file(tmp_path):
    """After analyze(), the state file must contain the market_id entry."""
    analyst = _make_analyst(tmp_path, llm_response=_json_response())
    analyst.analyze("0xpersist", "Q", "D", source_url="https://example.com")

    state_path = os.path.join(str(tmp_path), "research", "resolutions_cache.json")
    assert os.path.exists(state_path)
    with open(state_path) as f:
        data = json.load(f)
    assert "0xpersist" in data
    assert data["0xpersist"]["source_url"] == "https://example.com"


def test_cache_loaded_on_init(tmp_path):
    """A new analyst instance must load the existing cache and not re-call LLM."""
    # First analyst: analyze a market
    client1 = _make_llm_client(_json_response())
    analyst1 = _make_analyst(tmp_path, llm_client=client1)
    analyst1.analyze("0xcached", "Q", "D")
    assert client1.messages.create.call_count == 1

    # Second analyst with a fresh mock: cache already populated → no LLM call
    client2 = _make_llm_client(_json_response())
    analyst2 = PolyMarketAnalyst(
        base_path=str(tmp_path),
        prompt_path=_write_prompt(tmp_path),
        llm_client=client2,
    )
    analyst2.analyze("0xcached", "Q", "D")
    assert client2.messages.create.call_count == 0


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------

def test_parse_clean_json_response(tmp_path):
    """Clean JSON response must be parsed into a dict with 3 fields."""
    analyst = _make_analyst(tmp_path)
    raw = '{"boolean_condition": "ETH > 3K", "ambiguity_score": 2, "unexpected_risk_score": 1}'
    result = analyst._parse_response(raw)
    assert result["boolean_condition"] == "ETH > 3K"
    assert result["ambiguity_score"] == 2
    assert result["unexpected_risk_score"] == 1


def test_parse_json_embedded_in_text(tmp_path):
    """JSON embedded in prose must still be extracted correctly."""
    analyst = _make_analyst(tmp_path)
    raw = (
        'Here is my analysis:\n'
        '{"boolean_condition": "Team X wins", "ambiguity_score": 3, "unexpected_risk_score": 2}\n'
        'Hope this helps!'
    )
    result = analyst._parse_response(raw)
    assert result["boolean_condition"] == "Team X wins"
    assert result["ambiguity_score"] == 3


def test_parse_raises_on_invalid_response(tmp_path):
    """Garbage LLM output must raise ValueError."""
    analyst = _make_analyst(tmp_path)
    with pytest.raises(ValueError):
        analyst._parse_response("This market is really interesting and complex!")


# ---------------------------------------------------------------------------
# Analyze tests — 5 known markets
# ---------------------------------------------------------------------------

KNOWN_MARKETS = [
    ("0xbtc",     "Will BTC reach $100K by June 2026?",         "Resolves YES if BTC price...",    1, 1),
    ("0xelec",    "Who wins the 2026 US midterm elections?",     "Resolves YES if party X...",      3, 2),
    ("0xweather", "Will NYC see snow in July 2026?",             "Resolves YES if NYC records...",  2, 1),
    ("0xcrypto",  "Will ETH flip BTC by market cap in 2026?",   "Resolves YES if ETH market cap...", 2, 3),
    ("0xsports",  "Will team X win the championship?",           "Resolves YES if team X...",       1, 2),
]


@pytest.mark.parametrize("market_id,question,description,ambiguity,risk", KNOWN_MARKETS)
def test_analyze_5_known_markets(tmp_path, market_id, question, description, ambiguity, risk):
    """Each of the 5 known markets must parse correctly and return all 6 payload fields."""
    llm_response = _json_response(
        boolean_condition=f"Condition for {market_id}",
        ambiguity=ambiguity,
        risk=risk,
    )
    analyst = _make_analyst(tmp_path, llm_response=llm_response)
    result = analyst.analyze(market_id, question, description, source_url=f"https://poly/{market_id}")

    required_fields = {
        "market_id", "boolean_condition", "ambiguity_score",
        "unexpected_risk_score", "source_url", "analyzed_at",
    }
    assert required_fields == set(result.keys())
    assert result["market_id"] == market_id
    assert result["ambiguity_score"] == ambiguity
    assert result["unexpected_risk_score"] == risk
    assert result["source_url"] == f"https://poly/{market_id}"


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def test_analyze_publishes_bus_event(tmp_path):
    """analyze() must publish a signal:resolution_parsed event on the bus."""
    analyst = _make_analyst(tmp_path, llm_response=_json_response("BTC > 100K", 1, 1))
    analyst.analyze("0xbus_test", "Q", "D", source_url="https://example.com")

    bus_path = os.path.join(str(tmp_path), "bus", "pending_events.jsonl")
    assert os.path.exists(bus_path)

    events = []
    with open(bus_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    matching = [
        e for e in events
        if e.get("topic") == "signal:resolution_parsed"
        and e.get("producer") == "POLY_MARKET_ANALYST"
        and e["payload"].get("market_id") == "0xbus_test"
    ]
    assert len(matching) >= 1
    payload = matching[-1]["payload"]
    assert payload["boolean_condition"] == "BTC > 100K"
    assert payload["ambiguity_score"] == 1


def test_analyze_result_has_all_fields(tmp_path):
    """analyze() return value must contain all 6 required keys."""
    analyst = _make_analyst(tmp_path, llm_response=_json_response())
    result = analyst.analyze("0xfields", "Q", "D")
    required = {
        "market_id", "boolean_condition", "ambiguity_score",
        "unexpected_risk_score", "source_url", "analyzed_at",
    }
    assert required == set(result.keys())


def test_process_event_delegates_to_analyze(tmp_path):
    """process_event() with a full market payload must return same result as analyze()."""
    llm_response = _json_response("Snow in NYC in July", 2, 1)
    analyst = _make_analyst(tmp_path, llm_response=llm_response)

    payload = {
        "market_id": "0xsnow",
        "question": "Will NYC see snow in July 2026?",
        "description": "Resolves YES if any snow is recorded...",
        "source_url": "https://poly/snow",
    }
    result = analyst.process_event(payload)

    assert result["market_id"] == "0xsnow"
    assert result["boolean_condition"] == "Snow in NYC in July"
    assert result["ambiguity_score"] == 2


def test_cache_hit_does_not_publish_second_bus_event(tmp_path):
    """On cache hit, no new bus event must be published."""
    analyst = _make_analyst(tmp_path, llm_response=_json_response())
    analyst.analyze("0xonce", "Q", "D")
    analyst.analyze("0xonce", "Q", "D")  # cache hit

    bus_path = os.path.join(str(tmp_path), "bus", "pending_events.jsonl")
    events = []
    with open(bus_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    published = [
        e for e in events
        if e.get("topic") == "signal:resolution_parsed"
        and e["payload"].get("market_id") == "0xonce"
    ]
    assert len(published) == 1
