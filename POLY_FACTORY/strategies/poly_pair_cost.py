"""
POLY_PAIR_COST — Directional pair-cost arbitrage strategy.

Uses the opposite side's bid price as an implied fair-value reference to
identify mispriced directional entries in YES/NO binary markets.

Pair-cost logic:
  implied fair YES price  = 1.0 - no_bid
  implied fair NO  price  = 1.0 - yes_bid

  edge_yes = (1.0 - no_bid)  - yes_ask   → BUY_YES when > EDGE_THRESHOLD
  edge_no  = (1.0 - yes_bid) - no_ask    → BUY_NO  when > EDGE_THRESHOLD

  The side with the larger edge is chosen.  A minimum executability score
  from the market structure is required to filter illiquid markets.

Difference from POLY_ARB_SCANNER:
  ARB_SCANNER buys BOTH sides simultaneously (Dutch Book: yes_ask + no_ask < 0.97).
  PAIR_COST   buys ONE side directionally, using the opposite bid as the
              implied fair price.  Lower capital commitment per trade.

Consumes:
  signal:market_structure — executability filter (cache per market_id)
  feed:price_update       — triggers opportunity evaluation

Emits:
  trade:signal            — BUY_YES or BUY_NO

This module contains ONLY signal logic.  No execution, no order routing.
"""

from core.poly_audit_log import PolyAuditLog
from core.poly_event_bus import PolyEventBus


CONSUMER_ID = "POLY_PAIR_COST"
ACCOUNT_ID  = "ACC_POLY_PAIR_COST"
PLATFORM    = "polymarket"

# Strategy parameters (matches POLY_STRATEGY_REGISTRY v1.2)
EDGE_THRESHOLD     = 0.05   # min (implied_fair - ask) to emit a signal
MIN_EXECUTABILITY  = 60     # minimum executability_score from market structure
SUGGESTED_SIZE_EUR = 25.0   # suggested order size before Kelly sizing


class PolyPairCost:
    """Directional pair-cost arbitrage: exploits bid/ask asymmetry in YES/NO pairs.

    For each price update, computes the implied fair price of each side using
    the opposite side's bid, then signals the side offering the better entry
    relative to that implied fair price.
    """

    def __init__(self, base_path="state"):
        self.bus   = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        # In-memory cache of latest market structure per market_id
        self._market_structure = {}

    def _check_opportunity(
        self,
        market_id: str,
        yes_ask: float,
        yes_bid: float,
        no_ask: float,
        no_bid: float,
    ):
        """Evaluate a price update for a directional pair-cost opportunity.

        Pure function — no I/O, no side effects.

        Args:
            market_id: Market identifier.
            yes_ask:   Current YES ask price.
            yes_bid:   Current YES bid price.
            no_ask:    Current NO ask price.
            no_bid:    Current NO bid price.

        Returns:
            Signal payload dict if an opportunity is detected, else None.
        """
        # Check executability filter first
        structure = self._market_structure.get(market_id, {})
        if structure.get("executability_score", 0) < MIN_EXECUTABILITY:
            return None

        # Compute implied fair prices from the opposite side's bid
        edge_yes = (1.0 - no_bid)  - yes_ask   # how cheap YES is vs NO-implied fair
        edge_no  = (1.0 - yes_bid) - no_ask    # how cheap NO  is vs YES-implied fair

        # Choose the side with the largest edge; require it to exceed threshold
        if edge_yes >= edge_no and edge_yes > EDGE_THRESHOLD:
            direction = "BUY_YES"
            edge      = round(edge_yes, 6)
        elif edge_no > EDGE_THRESHOLD:
            direction = "BUY_NO"
            edge      = round(edge_no, 6)
        else:
            return None

        confidence = round(min(1.0, edge / (EDGE_THRESHOLD * 4)), 6)

        return {
            "strategy":          CONSUMER_ID,
            "account_id":        ACCOUNT_ID,
            "market_id":         market_id,
            "platform":          PLATFORM,
            "direction":         direction,
            "confidence":        confidence,
            "suggested_size_eur": SUGGESTED_SIZE_EUR,
            "signal_type":       "pair_cost",
            "signal_detail": {
                "yes_ask":  yes_ask,
                "yes_bid":  yes_bid,
                "no_ask":   no_ask,
                "no_bid":   no_bid,
                "edge_yes": round(edge_yes, 6),
                "edge_no":  round(edge_no,  6),
                "edge":     edge,
            },
        }

    def run_once(self) -> list:
        """Poll the bus for relevant events and emit signals for detected opportunities.

        Processing order within a batch:
        - signal:market_structure events update the executability cache first.
        - feed:price_update events are evaluated against the current cache.
        - All events are acked regardless of outcome.

        Returns:
            List of signal payload dicts that were published to the bus.
        """
        events = self.bus.poll(
            CONSUMER_ID,
            topics=["feed:price_update", "signal:market_structure"],
        )

        signals = []

        for evt in events:
            topic   = evt["topic"]
            payload = evt["payload"]

            if topic == "signal:market_structure":
                mid = payload.get("market_id")
                if mid:
                    self._market_structure[mid] = payload

            elif topic == "feed:price_update":
                mid     = payload.get("market_id")
                yes_ask = payload.get("yes_ask")
                yes_bid = payload.get("yes_bid")
                no_ask  = payload.get("no_ask")
                no_bid  = payload.get("no_bid")

                if mid and None not in (yes_ask, yes_bid, no_ask, no_bid):
                    signal = self._check_opportunity(mid, yes_ask, yes_bid, no_ask, no_bid)
                    if signal:
                        self.bus.publish("trade:signal", CONSUMER_ID, signal)
                        self.audit.log_event("trade:signal", CONSUMER_ID, signal)
                        signals.append(signal)

            self.bus.ack(CONSUMER_ID, evt["event_id"])

        return signals
