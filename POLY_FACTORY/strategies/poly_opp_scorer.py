"""
POLY_OPP_SCORER — LLM-powered high-probability opportunity scorer.

Uses Claude Sonnet to estimate the probability that a Polymarket binary market
resolves YES, based on the market's boolean resolution condition.  Signals BUY_YES
when the LLM-estimated probability meets the minimum threshold AND the market ask
price is low enough to offer a meaningful edge.

Strategy logic:
  1. Receive signal:resolution_parsed (boolean_condition, ambiguity_score,
     unexpected_risk_score) from POLY_MARKET_ANALYST.
  2. Call Claude Sonnet to estimate P(resolves YES) — result cached 4 hours per market.
  3. On each fresh resolution signal, compare LLM probability against the cached
     Polymarket YES ask.
  4. Emit BUY_YES when:
       - ambiguity_score < MAX_AMBIGUITY_SCORE (reject ambiguous criteria)
       - LLM probability >= MIN_LLM_PROBABILITY (0.75 — high-confidence YES)
       - edge (LLM_prob − yes_ask) > EDGE_THRESHOLD (0.05 — market mispriced)

LLM cost control:
  Each market is scored at most once per CACHE_TTL_SECONDS (4 hours).  The cache
  is persisted to disk so it survives process restarts.

Consumes:
  signal:resolution_parsed — boolean condition + quality scores (queue mode, 1x per market)
  feed:price_update        — current Polymarket YES ask (overwrite mode, per market_id)

Emits:
  trade:signal             — BUY_YES

This module contains ONLY signal logic.  No execution, no order routing.
"""

import json
import logging
import re
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_log_tokens import log_tokens


CONSUMER_ID = "POLY_OPP_SCORER"
ACCOUNT_ID  = "ACC_POLY_OPP_SCORER"
PLATFORM    = "polymarket"

# Strategy parameters
EDGE_THRESHOLD       = 0.05    # min (llm_prob - yes_ask) to emit a signal
MIN_LLM_PROBABILITY  = 0.75    # minimum LLM-estimated probability for BUY_YES
MAX_AMBIGUITY_SCORE  = 3       # reject markets with ambiguity_score >= this
CACHE_TTL_SECONDS    = 14_400  # 4 hours — max LLM call frequency per market
SUGGESTED_SIZE_EUR   = 25.0
LLM_MODEL            = "claude-sonnet-4-6"
LLM_MAX_TOKENS       = 250
LLM_CACHE_FILE       = "strategies/opp_scorer_llm_cache.json"


class PolyOppScorer:
    """LLM-scored high-probability YES opportunity detector.

    Accumulates resolution criteria from signal:resolution_parsed events and
    current ask prices from feed:price_update events.  On each fresh resolution
    signal the LLM is consulted (or the cache hit) to estimate P(YES), and a
    trade signal is emitted if the market is mispriced relative to that estimate.
    """

    def __init__(self, base_path="state", llm_client=None):
        self.store  = PolyDataStore(base_path=base_path)
        self.bus    = PolyEventBus(base_path=base_path)
        self.audit  = PolyAuditLog(base_path=base_path)

        # Injectable LLM client (None → lazy anthropic.Anthropic())
        self._llm_client = llm_client

        # In-memory caches keyed by market_id
        self._resolution_cache = {}   # market_id → signal:resolution_parsed payload
        self._price_cache      = {}   # market_id → feed:price_update payload
        self._llm_cache        = self._load_llm_cache()

    # ------------------------------------------------------------------
    # LLM cache helpers
    # ------------------------------------------------------------------

    def _load_llm_cache(self) -> dict:
        """Load the persisted LLM score cache from disk."""
        data = self.store.read_json(LLM_CACHE_FILE)
        return data if data is not None else {}

    def _save_llm_cache(self) -> None:
        """Persist the in-memory LLM cache to disk."""
        self.store.write_json(LLM_CACHE_FILE, self._llm_cache)

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    def _get_llm_client(self):
        """Return the LLM client, instantiating lazily if needed."""
        if self._llm_client is None:
            import anthropic  # deferred — avoids import error in test environments
            self._llm_client = anthropic.Anthropic()
        return self._llm_client

    def _build_prompt(
        self,
        boolean_condition: str,
        ambiguity_score: int,
        unexpected_risk_score: int,
        yes_ask: float = 0.0,
    ) -> str:
        """Build the adversarial LLM prompt for opportunity scoring."""
        no_price = 1.0 - yes_ask
        return (
            "You are a prediction market analyst.\n"
            "The market price reflects aggregated information from many traders.\n"
            "Your job is NOT to estimate blindly, but to determine "
            "if there is a real mispricing.\n\n"
            f"Condition: {boolean_condition}\n"
            f"Ambiguity: {ambiguity_score}/10 | Risk: {unexpected_risk_score}/10\n"
            f"Market price: YES={yes_ask:.1%} / NO={no_price:.1%}\n\n"
            "Steps:\n"
            "1. What is the base rate?\n"
            "2. What information could the market be using?\n"
            "3. Do I have a specific reason to disagree with the market?\n"
            "4. Is this disagreement strong enough to create an edge?\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"probability": <float 0.0-1.0>, "has_edge": true|false, '
            '"edge_strength": "none|weak|moderate|strong", '
            '"reasoning": "<1 sentence>", '
            '"why_market_might_be_right": "<1 sentence>", '
            '"confidence": "low|medium|high"}'
        )

    def _call_llm(
        self,
        boolean_condition: str,
        ambiguity_score: int,
        unexpected_risk_score: int,
        yes_ask: float = 0.0,
    ) -> str:
        """Call Claude Sonnet and return the raw text response."""
        prompt = self._build_prompt(boolean_condition, ambiguity_score, unexpected_risk_score, yes_ask)
        client = self._get_llm_client()
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        log_tokens(
            self.store.base_path,
            "POLY_OPP_SCORER",
            LLM_MODEL,
            response.usage.input_tokens,
            response.usage.output_tokens,
            task="opp_scoring",
        )
        return response.content[0].text

    def _parse_llm_response(self, raw_text: str) -> dict:
        """Extract structured LLM response with adversarial fields.

        Returns:
            Dict with prob_yes, reasoning, has_edge, edge_strength, confidence.
        """
        def _extract(data):
            return {
                "probability": float(data["probability"]),
                "reasoning": str(data.get("reasoning", "")),
                "has_edge": bool(data.get("has_edge", False)),
                "edge_strength": str(data.get("edge_strength", "none")),
                "confidence": str(data.get("confidence", "low")),
            }

        try:
            return _extract(json.loads(raw_text.strip()))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass

        match = re.search(r'\{[^{}]*\}', raw_text, re.DOTALL)
        if match:
            try:
                return _extract(json.loads(match.group()))
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                pass

        raise ValueError(f"Could not parse LLM response: {raw_text[:200]!r}")

    # ------------------------------------------------------------------
    # Cache freshness
    # ------------------------------------------------------------------

    def _is_cache_fresh(self, market_id: str) -> bool:
        """Return True if the cached LLM score for market_id is within TTL."""
        entry = self._llm_cache.get(market_id)
        if not entry:
            return False
        age = datetime.now(timezone.utc).timestamp() - entry.get("timestamp", 0)
        return age < CACHE_TTL_SECONDS

    def _get_llm_score(self, market_id: str, resolution_payload: dict, yes_ask: float = 0.0) -> dict:
        """Return LLM score dict, using cache when fresh.

        Returns:
            Dict with probability, reasoning, has_edge, edge_strength, confidence.
        """
        if self._is_cache_fresh(market_id):
            return self._llm_cache[market_id]

        boolean_condition     = resolution_payload.get("boolean_condition", "")
        ambiguity_score       = resolution_payload.get("ambiguity_score", 0)
        unexpected_risk_score = resolution_payload.get("unexpected_risk_score", 0)

        raw = self._call_llm(boolean_condition, ambiguity_score, unexpected_risk_score, yes_ask)
        result = self._parse_llm_response(raw)

        self._llm_cache[market_id] = {
            **result,
            "timestamp": datetime.now(timezone.utc).timestamp(),
        }
        self._save_llm_cache()

        return result

    # ------------------------------------------------------------------
    # Pure opportunity check
    # ------------------------------------------------------------------

    def _check_opportunity(
        self,
        market_id: str,
        resolution_payload: dict,
        price_payload: dict,
    ):
        """Evaluate a market for a high-probability BUY_YES opportunity.

        Args:
            market_id:          Market identifier.
            resolution_payload: signal:resolution_parsed payload dict.
            price_payload:      feed:price_update payload dict.

        Returns:
            Signal payload dict if an opportunity is detected, else None.
        """
        # Reject ambiguous markets
        if resolution_payload.get("ambiguity_score", 10) >= MAX_AMBIGUITY_SCORE:
            return None

        yes_ask = price_payload.get("yes_ask")
        if yes_ask is None:
            return None

        llm = self._get_llm_score(market_id, resolution_payload, yes_ask)
        probability = llm["probability"]
        has_edge = llm.get("has_edge", False)
        edge_strength = llm.get("edge_strength", "none")
        llm_confidence = llm.get("confidence", "low")

        # Log every LLM decision for post-analysis (print → pm2-out.log)
        print(
            f"LLM_DECISION | strategy={CONSUMER_ID} | market={market_id[:16]} | "
            f"has_edge={has_edge} | edge_strength={edge_strength} | "
            f"confidence={llm_confidence} | prob={probability:.3f} | yes_ask={yes_ask:.3f}"
        )

        # Adversarial gate: only emit signal if LLM confirms edge
        if not has_edge or edge_strength in ("none", "weak") or llm_confidence == "low":
            return None

        if probability < MIN_LLM_PROBABILITY:
            return None

        edge = probability - yes_ask
        if edge <= EDGE_THRESHOLD:
            return None

        confidence = round(min(1.0, edge / (EDGE_THRESHOLD * 4)), 6)

        return {
            "strategy":           CONSUMER_ID,
            "account_id":         ACCOUNT_ID,
            "market_id":          market_id,
            "platform":           PLATFORM,
            "direction":          "BUY_YES",
            "confidence":         confidence,
            "suggested_size_eur": SUGGESTED_SIZE_EUR,
            "signal_type":        "opp_scorer",
            "signal_detail": {
                "boolean_condition":     resolution_payload.get("boolean_condition"),
                "llm_probability":       round(probability, 6),
                "yes_ask":               yes_ask,
                "edge":                  round(edge, 6),
                "has_edge":              has_edge,
                "edge_strength":         edge_strength,
                "llm_confidence":        llm_confidence,
                "ambiguity_score":       resolution_payload.get("ambiguity_score"),
                "unexpected_risk_score": resolution_payload.get("unexpected_risk_score"),
                "reasoning":             llm.get("reasoning", ""),
            },
        }

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_once(self) -> list:
        """Poll the bus, update caches, emit signals for fresh resolution events.

        Processing order:
        - feed:price_update events update the Polymarket price cache.
        - signal:resolution_parsed events update the resolution cache and mark
          the market as needing evaluation.
        - After all events are processed, each updated market is evaluated.
        - All events are acked regardless of outcome.

        Returns:
            List of trade:signal payload dicts published to the bus.
        """
        events = self.bus.poll(
            CONSUMER_ID,
            topics=["feed:price_update", "signal:resolution_parsed"],
        )

        updated_markets = set()

        for evt in events:
            topic   = evt["topic"]
            payload = evt["payload"]

            if topic == "feed:price_update":
                mid = payload.get("market_id")
                if mid:
                    self._price_cache[mid] = payload

            elif topic == "signal:resolution_parsed":
                mid = payload.get("market_id")
                if mid:
                    self._resolution_cache[mid] = payload
                    updated_markets.add(mid)

            self.bus.ack(CONSUMER_ID, evt["event_id"])

        signals = []
        for mid in updated_markets:
            resolution = self._resolution_cache.get(mid)
            price      = self._price_cache.get(mid)
            if resolution and price:
                signal = self._check_opportunity(mid, resolution, price)
                if signal:
                    self.bus.publish("trade:signal", CONSUMER_ID, signal)
                    self.audit.log_event("trade:signal", CONSUMER_ID, signal)
                    signals.append(signal)

        return signals
