"""
POLY_MARKET_ANALYST — Resolution criteria parser for POLY_FACTORY.

Calls Claude Sonnet to parse a Polymarket market's resolution criteria into:
  - boolean_condition: concise YES-resolution sentence
  - ambiguity_score: 0-10 (Filter 2 blocks trades if >= 3)
  - unexpected_risk_score: 0-10

Results are cached in state/research/resolutions_cache.json with a 48-hour TTL.
Publishes signal:resolution_parsed on new or refreshed analysis.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_log_tokens import log_tokens

logger = logging.getLogger("POLY_MARKET_ANALYST")

CACHE_STATE_FILE = "research/resolutions_cache.json"
PROMPT_FILE = "prompts/resolution_parser_prompt.txt"
LLM_MODEL = "claude-sonnet-4-6"
LLM_MAX_TOKENS = 500
CACHE_TTL_SECONDS = 4 * 3600  # 4 hours — rotates all active markets every ~4h
REPROCESS_BATCH_SIZE = 10     # max markets reanalyzed per run_once() cycle


class PolyMarketAnalyst:
    """Parses market resolution criteria via Claude Sonnet with per-market caching."""

    def __init__(self, base_path="state", prompt_path=None, llm_client=None):
        """Initialize the market analyst.

        Args:
            base_path: Base path for state files.
            prompt_path: Path to resolution_parser_prompt.txt. Defaults to
                prompts/resolution_parser_prompt.txt relative to project root.
            llm_client: Anthropic client instance. If None, instantiated lazily
                on first LLM call (avoids import errors in test environments
                that don't have the anthropic package or API key).
        """
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)

        if prompt_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            prompt_path = os.path.join(project_root, PROMPT_FILE)

        with open(prompt_path, "r", encoding="utf-8") as f:
            self._prompt_template = f.read()

        # Injected client (used for testing); None = instantiate on first use
        self._llm_client = llm_client

        # Load existing cache from state file
        self._cache = self._load_cache()

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _load_cache(self):
        """Load the resolutions cache from the state file.

        Returns:
            Dict mapping market_id → cached result. Empty dict if not found.
        """
        data = self.store.read_json(CACHE_STATE_FILE)
        return data if data is not None else {}

    def _save_cache(self):
        """Persist the in-memory cache to the state file."""
        self.store.write_json(CACHE_STATE_FILE, self._cache)

    def _is_cache_fresh(self, market_id):
        """Return True if the cached entry for market_id exists and is within TTL.

        Entries without a ``cached_at`` timestamp (legacy) are treated as expired.
        """
        entry = self._cache.get(market_id)
        if not entry:
            return False
        cached_at = entry.get("cached_at")
        if cached_at is None:
            return False
        age = datetime.now(timezone.utc).timestamp() - cached_at
        return age < CACHE_TTL_SECONDS

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    def _get_llm_client(self):
        """Return the LLM client, instantiating it lazily if needed."""
        if self._llm_client is None:
            import anthropic  # deferred to avoid import error when mocked
            self._llm_client = anthropic.Anthropic()
        return self._llm_client

    def _build_prompt(self, question, description):
        """Substitute placeholders in the prompt template.

        Uses .replace() instead of .format() because the template contains
        literal JSON braces in the example line that would break .format().

        Args:
            question: Market question string.
            description: Market description / resolution rules.

        Returns:
            Formatted prompt string.
        """
        return (
            self._prompt_template
            .replace("{question}", question)
            .replace("{description}", description)
        )

    def _call_llm(self, prompt):
        """Call Claude Sonnet and return the raw text response.

        Args:
            prompt: Formatted prompt string.

        Returns:
            Raw text content from the first content block.
        """
        client = self._get_llm_client()
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        log_tokens(
            self.store.base_path,
            "POLY_MARKET_ANALYST",
            LLM_MODEL,
            response.usage.input_tokens,
            response.usage.output_tokens,
            task="resolution_parse",
        )
        return response.content[0].text

    def _parse_response(self, raw_text):
        """Extract the JSON payload from LLM response text.

        Handles both clean JSON responses and JSON embedded in prose.

        Args:
            raw_text: Raw string from LLM.

        Returns:
            Dict with boolean_condition (str), ambiguity_score (int),
            unexpected_risk_score (int).

        Raises:
            ValueError: If no valid JSON with required fields is found.
        """
        # Try direct parse first
        try:
            data = json.loads(raw_text.strip())
            return self._validate_parsed(data)
        except (json.JSONDecodeError, ValueError):
            pass

        # Extract first JSON object from prose
        match = re.search(r'\{[^{}]*\}', raw_text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return self._validate_parsed(data)
            except (json.JSONDecodeError, ValueError):
                pass

        raise ValueError(f"Could not extract valid JSON from LLM response: {raw_text[:200]!r}")

    def _validate_parsed(self, data):
        """Validate that parsed dict has all required fields.

        Args:
            data: Parsed dict from LLM response.

        Returns:
            Validated dict.

        Raises:
            ValueError: If required fields are missing or wrong type.
        """
        required = ("boolean_condition", "ambiguity_score", "unexpected_risk_score")
        for field in required:
            if field not in data:
                raise ValueError(f"Missing field '{field}' in LLM response")

        return {
            "boolean_condition": str(data["boolean_condition"]),
            "ambiguity_score": int(data["ambiguity_score"]),
            "unexpected_risk_score": int(data["unexpected_risk_score"]),
        }

    # ------------------------------------------------------------------
    # Public pipeline
    # ------------------------------------------------------------------

    def analyze(self, market_id, question, description, source_url=""):
        """Parse resolution criteria for a market, using cache when available.

        On cache hit: returns cached entry immediately, no LLM call.
        On cache miss: calls LLM, parses response, caches and publishes result.

        Args:
            market_id: Unique market identifier.
            question: Market question text.
            description: Resolution rules / description text.
            source_url: Optional URL for the market page.

        Returns:
            Dict with market_id, boolean_condition, ambiguity_score,
            unexpected_risk_score, source_url, analyzed_at.
        """
        if self._is_cache_fresh(market_id):
            logger.debug("Cache hit for market %s", market_id)
            entry = self._cache[market_id]
            return {k: v for k, v in entry.items() if k != "cached_at"}

        logger.info("Analyzing market %s via LLM", market_id)
        prompt = self._build_prompt(question, description)
        raw_text = self._call_llm(prompt)
        parsed = self._parse_response(raw_text)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = {
            "market_id": market_id,
            "boolean_condition": parsed["boolean_condition"],
            "ambiguity_score": parsed["ambiguity_score"],
            "unexpected_risk_score": parsed["unexpected_risk_score"],
            "source_url": source_url,
            "analyzed_at": now,
        }

        self._cache[market_id] = {**result, "cached_at": datetime.now(timezone.utc).timestamp()}
        self._save_cache()

        self.bus.publish(
            topic="signal:resolution_parsed",
            producer="POLY_MARKET_ANALYST",
            payload={
                "market_id": market_id,
                "boolean_condition": result["boolean_condition"],
                "ambiguity_score": result["ambiguity_score"],
                "unexpected_risk_score": result["unexpected_risk_score"],
                "source_url": source_url,
            },
            priority="normal",
        )

        return result

    def process_event(self, market_payload):
        """Handle a market:new_detected bus event payload.

        Args:
            market_payload: Dict with market_id, question, description,
                and optionally source_url.

        Returns:
            Analysis result dict.
        """
        return self.analyze(
            market_id=market_payload.get("market_id", ""),
            question=market_payload.get("question", ""),
            description=market_payload.get("description", ""),
            source_url=market_payload.get("source_url", ""),
        )

    def run_once(self):
        """Analyze active markets whose cache has expired (oldest first).

        Reads the active markets list written by the connector and selects
        markets whose cache is stale or missing, ordered by oldest cached_at
        first (anti-starvation).  At most REPROCESS_BATCH_SIZE markets are
        analyzed per cycle to avoid flooding the bus or LLM.

        Returns:
            List of newly analyzed result dicts.
        """
        markets = self.store.read_json("feeds/active_markets.json") or []

        # Collect eligible markets (stale or uncached)
        eligible = []
        for m in markets:
            mid = m.get("market_id", "")
            if not mid or self._is_cache_fresh(mid):
                continue
            # Sort key: cached_at timestamp (0 if never cached → highest priority)
            cached_at = 0
            entry = self._cache.get(mid)
            if entry and entry.get("cached_at"):
                cached_at = entry["cached_at"]
            eligible.append((cached_at, m))

        # Oldest first, then cap to batch size
        eligible.sort(key=lambda x: x[0])
        batch = eligible[:REPROCESS_BATCH_SIZE]

        if eligible:
            logger.info(
                "run_once: %d eligible market(s), processing batch of %d",
                len(eligible), len(batch),
            )

        results = []
        for _, m in batch:
            mid = m.get("market_id", "")
            try:
                result = self.analyze(
                    market_id=mid,
                    question=m.get("question", ""),
                    description=m.get("description", ""),
                )
                results.append(result)
            except Exception:
                logger.warning("Failed to analyze market %s", mid, exc_info=True)

        if results:
            logger.info("run_once: analyzed %d market(s) this cycle", len(results))
        return results
