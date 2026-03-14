"""
POLY_NO_SCANNER — LLM-powered high-probability NO opportunity scanner.

Uses Claude Haiku to estimate the probability that a Polymarket binary market
resolves YES, based on the market's boolean resolution condition.  Signals BUY_NO
when the market strongly believes the event will NOT resolve YES (no_ask ≥ 90 cents)
AND Haiku confirms P(NO) ≥ 90% with meaningful edge.

Key differences from POLY_OPP_SCORER:
  - Direction: BUY_NO (not BUY_YES)
  - LLM: Claude Haiku (cheaper) instead of Sonnet
  - Cache: permanent (no TTL) — each market is scored exactly once, ever
  - Screen: no_ask ≥ MIN_NO_ASK (90 cents) instead of YES ask threshold

Strategy logic:
  1. Receive feed:price_update — track no_ask per market.
  2. Receive signal:resolution_parsed — boolean_condition, ambiguity_score,
     unexpected_risk_score from POLY_MARKET_ANALYST.
  3. On fresh resolution event: skip markets where no_ask < MIN_NO_ASK or
     ambiguity_score is too high.
  4. Call Haiku once per market (permanent cache) to estimate P(YES).
  5. Derive P(NO) = 1 - P(YES).
  6. Emit BUY_NO when: P(NO) ≥ MIN_LLM_PROBABILITY_NO AND edge > EDGE_THRESHOLD.

Consumes:
  feed:price_update        — current Polymarket prices (overwrite mode, per market_id)
  signal:resolution_parsed — boolean condition + quality scores (queue mode, 1x per market)

Emits:
  trade:signal             — BUY_NO

This module contains ONLY signal logic.  No execution, no order routing.
"""

import json
import re

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_log_tokens import log_tokens


CONSUMER_ID            = "POLY_NO_SCANNER"
ACCOUNT_ID             = "ACC_POLY_NO_SCANNER"
PLATFORM               = "polymarket"

# Strategy parameters
MIN_NO_ASK             = 0.90    # screen: NO must cost ≥ 90 cents (YES very cheap)
EDGE_THRESHOLD         = 0.03    # min (prob_no - no_ask) to emit a signal
MIN_LLM_PROBABILITY_NO = 0.90    # Haiku must estimate P(NO) ≥ 90%
MAX_AMBIGUITY_SCORE    = 3       # reject markets with ambiguity_score >= this
SUGGESTED_SIZE_EUR     = 20.0    # smaller size — conservative NO bet
LLM_MODEL              = "claude-haiku-4-5-20251001"
LLM_MAX_TOKENS         = 150
LLM_CACHE_FILE         = "strategies/no_scanner_llm_cache.json"


class PolyNoScanner:
    """LLM-scored high-probability NO opportunity detector.

    Accumulates resolution criteria from signal:resolution_parsed events and
    current prices from feed:price_update events.  On each fresh resolution
    signal, if the no_ask passes the minimum screen, Haiku is consulted once
    (permanently cached) to estimate P(YES); a BUY_NO trade signal is emitted
    if P(NO) ≥ MIN_LLM_PROBABILITY_NO and edge > EDGE_THRESHOLD.
    """

    def __init__(self, base_path="state", llm_client=None):
        self.store = PolyDataStore(base_path=base_path)
        self.bus   = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)

        # Injectable LLM client (None → lazy anthropic.Anthropic())
        self._llm_client = llm_client

        # In-memory caches keyed by market_id
        self._resolution_cache = {}   # market_id → signal:resolution_parsed payload
        self._price_cache      = {}   # market_id → feed:price_update payload
        self._llm_cache        = self._load_llm_cache()

    # ------------------------------------------------------------------
    # LLM cache helpers — permanent (no TTL)
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
    ) -> str:
        """Build the LLM prompt for NO opportunity scoring."""
        return (
            "You are evaluating a prediction market resolution condition.\n\n"
            f"Condition: {boolean_condition}\n"
            f"Ambiguity score: {ambiguity_score}/10 (higher = more ambiguous)\n"
            f"Unexpected risk score: {unexpected_risk_score}/10 (higher = more uncertain)\n\n"
            "What is the probability (0.0-1.0) that this market resolves YES?\n"
            'Respond with ONLY valid JSON: {"probability": <float 0.0-1.0>, "reasoning": "<1 sentence>"}'
        )

    def _call_llm(
        self,
        boolean_condition: str,
        ambiguity_score: int,
        unexpected_risk_score: int,
    ) -> str:
        """Call Claude Haiku and return the raw text response."""
        prompt = self._build_prompt(boolean_condition, ambiguity_score, unexpected_risk_score)
        client = self._get_llm_client()
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        log_tokens(
            self.store.base_path,
            "POLY_NO_SCANNER",
            LLM_MODEL,
            response.usage.input_tokens,
            response.usage.output_tokens,
            task="no_scoring",
        )
        return response.content[0].text

    def _parse_llm_response(self, raw_text: str) -> tuple:
        """Extract (prob_yes, reasoning) from LLM response text.

        Tries direct JSON parse first, then falls back to extracting the first
        JSON object from prose.

        Args:
            raw_text: Raw string from the LLM.

        Returns:
            Tuple of (prob_yes: float, reasoning: str).

        Raises:
            ValueError: If no valid JSON with a 'probability' field is found.
        """
        # Direct parse
        try:
            data = json.loads(raw_text.strip())
            return float(data["probability"]), str(data.get("reasoning", ""))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass

        # Extract from prose
        match = re.search(r'\{[^{}]*\}', raw_text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return float(data["probability"]), str(data.get("reasoning", ""))
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                pass

        raise ValueError(f"Could not parse LLM response: {raw_text[:200]!r}")

    # ------------------------------------------------------------------
    # Permanent cache check (no TTL)
    # ------------------------------------------------------------------

    def _is_cached(self, market_id: str) -> bool:
        """Return True if this market has ever been scored (permanent cache)."""
        return market_id in self._llm_cache

    def _get_llm_score(self, market_id: str, resolution_payload: dict) -> tuple:
        """Return (prob_yes, reasoning), using permanent cache when available.

        Args:
            market_id:          Market identifier.
            resolution_payload: signal:resolution_parsed payload dict.

        Returns:
            Tuple (prob_yes: float, reasoning: str).
        """
        if self._is_cached(market_id):
            entry = self._llm_cache[market_id]
            return entry["prob_yes"], entry["reasoning"]

        boolean_condition     = resolution_payload.get("boolean_condition", "")
        ambiguity_score       = resolution_payload.get("ambiguity_score", 0)
        unexpected_risk_score = resolution_payload.get("unexpected_risk_score", 0)

        raw = self._call_llm(boolean_condition, ambiguity_score, unexpected_risk_score)
        prob_yes, reasoning = self._parse_llm_response(raw)

        # Permanent cache — no timestamp needed
        self._llm_cache[market_id] = {
            "prob_yes":  prob_yes,
            "reasoning": reasoning,
        }
        self._save_llm_cache()

        return prob_yes, reasoning

    # ------------------------------------------------------------------
    # Pure opportunity check
    # ------------------------------------------------------------------

    def _check_opportunity(
        self,
        market_id: str,
        resolution_payload: dict,
        price_payload: dict,
    ):
        """Evaluate a market for a high-probability BUY_NO opportunity.

        Args:
            market_id:          Market identifier.
            resolution_payload: signal:resolution_parsed payload dict.
            price_payload:      feed:price_update payload dict.

        Returns:
            Signal payload dict if an opportunity is detected, else None.
        """
        no_ask = price_payload.get("no_ask")
        if no_ask is None:
            return None

        # Only scan near-certain-NO markets (NO costs ≥ 90 cents)
        if no_ask < MIN_NO_ASK:
            return None

        # Reject ambiguous markets
        if resolution_payload.get("ambiguity_score", 10) >= MAX_AMBIGUITY_SCORE:
            return None

        prob_yes, reasoning = self._get_llm_score(market_id, resolution_payload)
        prob_no = 1.0 - prob_yes

        if prob_no < MIN_LLM_PROBABILITY_NO:
            return None

        edge = prob_no - no_ask
        if edge <= EDGE_THRESHOLD:
            return None

        confidence = round(min(1.0, edge / (EDGE_THRESHOLD * 4)), 6)

        return {
            "strategy":           CONSUMER_ID,
            "account_id":         ACCOUNT_ID,
            "market_id":          market_id,
            "platform":           PLATFORM,
            "direction":          "BUY_NO",
            "confidence":         confidence,
            "suggested_size_eur": SUGGESTED_SIZE_EUR,
            "signal_type":        "no_scanner",
            "signal_detail": {
                "boolean_condition":     resolution_payload.get("boolean_condition"),
                "prob_yes":              round(prob_yes, 6),
                "prob_no":               round(prob_no, 6),
                "no_ask":                no_ask,
                "edge":                  round(edge, 6),
                "ambiguity_score":       resolution_payload.get("ambiguity_score"),
                "unexpected_risk_score": resolution_payload.get("unexpected_risk_score"),
                "reasoning":             reasoning,
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
