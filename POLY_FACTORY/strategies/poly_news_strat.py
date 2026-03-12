"""
POLY_NEWS_STRAT — News-impact directional signal strategy.

Reacts to high-impact news events (news:high_impact) affecting a prediction
market.  The news is pre-scored externally by the OpenClaw NEWS_SCORING system
before it reaches this strategy — no LLM is needed here.

Strategy logic:
  1. Receive news:high_impact (priority bus mode) from OpenClaw NEWS_FEED.
  2. Require feed:price_update to be cached for the same market (price gate:
     prevents betting into a market that has already priced in the news).
  3. Emit trade:signal when:
       - impact_score >= MIN_IMPACT_SCORE (0.70)
       - sentiment != "NEUTRAL"
       - POSITIVE: yes_ask <= MAX_YES_ASK (0.80)
       - NEGATIVE: no_ask  <= MAX_NO_ASK  (0.80)

Direction: POSITIVE → BUY_YES, NEGATIVE → BUY_NO, NEUTRAL → skip.
Confidence = impact_score (already 0-1, represents conviction).

No LLM calls — pure deterministic logic.

Consumes:
  news:high_impact   — trigger + news data (priority mode, from OpenClaw NEWS_FEED)
  feed:price_update  — current ask prices (overwrite mode, per market_id)

Emits:
  trade:signal — BUY_YES or BUY_NO

This module contains ONLY signal logic.  No execution, no order routing.
"""

from core.poly_audit_log import PolyAuditLog
from core.poly_event_bus import PolyEventBus


CONSUMER_ID        = "POLY_NEWS_STRAT"
ACCOUNT_ID         = "ACC_POLY_NEWS_STRAT"
PLATFORM           = "polymarket"

# Strategy parameters
MIN_IMPACT_SCORE   = 0.70    # minimum news impact score to act on
MAX_YES_ASK        = 0.80    # reject BUY_YES if market already priced in the news
MAX_NO_ASK         = 0.80    # reject BUY_NO if market already priced in the news
SUGGESTED_SIZE_EUR = 20.0


class PolyNewsStrat:
    """News-impact directional signal strategy.

    Accumulates current ask prices from feed:price_update events and latest
    news from news:high_impact events.  On each fresh news event the market is
    evaluated against both caches and a trade signal is emitted when all
    filters pass.
    """

    def __init__(self, base_path="state"):
        self.bus   = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)

        # In-memory caches keyed by market_id
        self._price_cache = {}   # market_id → feed:price_update payload
        self._news_cache  = {}   # market_id → latest news:high_impact payload

    # ------------------------------------------------------------------
    # Pure opportunity check
    # ------------------------------------------------------------------

    def _check_opportunity(
        self,
        market_id: str,
        news_payload: dict,
        price_payload: dict,
    ):
        """Evaluate a market for a news-impact trade opportunity.

        Args:
            market_id:     Market identifier.
            news_payload:  news:high_impact payload dict.
            price_payload: feed:price_update payload dict.

        Returns:
            Signal payload dict if an opportunity is detected, else None.
        """
        impact_score = news_payload.get("impact_score", 0.0)
        if impact_score < MIN_IMPACT_SCORE:
            return None

        sentiment = news_payload.get("sentiment", "NEUTRAL")
        if sentiment == "NEUTRAL":
            return None

        if sentiment == "POSITIVE":
            yes_ask = price_payload.get("yes_ask")
            if yes_ask is None or yes_ask > MAX_YES_ASK:
                return None
            direction  = "BUY_YES"
            ask_detail = {"yes_ask": yes_ask}

        elif sentiment == "NEGATIVE":
            no_ask = price_payload.get("no_ask")
            if no_ask is None or no_ask > MAX_NO_ASK:
                return None
            direction  = "BUY_NO"
            ask_detail = {"no_ask": no_ask}

        else:
            return None

        confidence = round(min(1.0, impact_score), 6)

        signal_detail = {
            "headline":     news_payload.get("headline"),
            "impact_score": impact_score,
            "sentiment":    sentiment,
            "source":       news_payload.get("source"),
            "published_at": news_payload.get("published_at"),
        }
        signal_detail.update(ask_detail)

        return {
            "strategy":           CONSUMER_ID,
            "account_id":         ACCOUNT_ID,
            "market_id":          market_id,
            "platform":           PLATFORM,
            "direction":          direction,
            "confidence":         confidence,
            "suggested_size_eur": SUGGESTED_SIZE_EUR,
            "signal_type":        "news_impact",
            "signal_detail":      signal_detail,
        }

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_once(self) -> list:
        """Poll the bus, update caches, emit signals for fresh news events.

        Processing order:
        - feed:price_update events update the price cache (no trigger).
        - news:high_impact events update the news cache and mark the market
          as needing evaluation.
        - After all events are processed, each updated market is evaluated.
        - All events are acked regardless of outcome.

        Returns:
            List of trade:signal payload dicts published to the bus.
        """
        events = self.bus.poll(
            CONSUMER_ID,
            topics=["news:high_impact", "feed:price_update"],
        )

        updated_markets = set()

        for evt in events:
            topic   = evt["topic"]
            payload = evt["payload"]

            if topic == "feed:price_update":
                mid = payload.get("market_id")
                if mid:
                    self._price_cache[mid] = payload

            elif topic == "news:high_impact":
                mid = payload.get("market_id")
                if mid:
                    self._news_cache[mid] = payload
                    updated_markets.add(mid)

            self.bus.ack(CONSUMER_ID, evt["event_id"])

        signals = []
        for mid in updated_markets:
            news  = self._news_cache.get(mid)
            price = self._price_cache.get(mid)
            if news and price:
                signal = self._check_opportunity(mid, news, price)
                if signal:
                    self.bus.publish("trade:signal", CONSUMER_ID, signal)
                    self.audit.log_event("trade:signal", CONSUMER_ID, signal)
                    signals.append(signal)

        return signals
