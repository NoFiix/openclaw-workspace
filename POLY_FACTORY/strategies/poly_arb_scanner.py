"""
POLY_ARB_SCANNER — Bundle YES+NO arbitrage (Dutch Book) detection strategy.

Consumes feed:price_update and signal:market_structure events.
Emits trade:signal when yes_ask + no_ask < SUM_THRESHOLD and the market
passes the minimum executability filter.

This module contains ONLY signal logic. No execution, no order routing.
"""

from core.poly_audit_log import PolyAuditLog
from core.poly_event_bus import PolyEventBus


CONSUMER_ID = "POLY_ARB_SCANNER"
ACCOUNT_ID = "ACC_POLY_ARB_SCANNER"
PLATFORM = "polymarket"

# Strategy parameters (matches POLY_STRATEGY_REGISTRY v1.2)
SUM_THRESHOLD = 0.97        # signal when yes_ask + no_ask < this value
MIN_EXECUTABILITY = 60      # minimum executability_score from market structure
SUGGESTED_SIZE_EUR = 30.0   # suggested order size before Kelly sizing


class PolyArbScanner:
    """Bundle arbitrage strategy: detects Dutch Book opportunities on Polymarket.

    A Dutch Book exists when the sum of YES ask and NO ask prices is below 1.0,
    meaning both sides can be bought for less than their guaranteed combined payout.
    We use a conservative threshold of 0.97 to filter out noise and fees.
    """

    def __init__(self, base_path="state"):
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        # In-memory cache of latest market structure per market_id
        self._market_structure = {}

    def _check_opportunity(self, market_id: str, yes_ask: float, no_ask: float):
        """Evaluate a price update for a bundle arbitrage opportunity.

        Args:
            market_id: Market identifier.
            yes_ask: Current YES ask price.
            no_ask: Current NO ask price.

        Returns:
            Signal payload dict if an opportunity is detected, else None.
        """
        ask_sum = yes_ask + no_ask

        if ask_sum >= SUM_THRESHOLD:
            return None

        structure = self._market_structure.get(market_id, {})
        if structure.get("executability_score", 0) < MIN_EXECUTABILITY:
            return None

        spread = round(SUM_THRESHOLD - ask_sum, 6)
        confidence = round(min(1.0, spread / SUM_THRESHOLD), 6)

        return {
            "strategy": CONSUMER_ID,
            "account_id": ACCOUNT_ID,
            "market_id": market_id,
            "platform": PLATFORM,
            "direction": "BUY_YES_AND_NO",
            "confidence": confidence,
            "suggested_size_eur": SUGGESTED_SIZE_EUR,
            "signal_type": "bundle_arb",
            "signal_detail": {
                "yes_ask": yes_ask,
                "no_ask": no_ask,
                "spread": spread,
            },
        }

    def run_once(self) -> list:
        """Poll the bus for relevant events and emit signals for detected opportunities.

        Processing order within a batch:
        - signal:market_structure events update the in-memory cache first (sorted by
          timestamp, so earlier events processed first — market structure published
          before price updates will be in cache when price events are evaluated).
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
            topic = evt["topic"]
            payload = evt["payload"]

            if topic == "signal:market_structure":
                market_id = payload.get("market_id")
                if market_id:
                    self._market_structure[market_id] = payload

            elif topic == "feed:price_update":
                market_id = payload.get("market_id")
                yes_ask = payload.get("yes_ask")
                no_ask = payload.get("no_ask")

                if market_id and yes_ask is not None and no_ask is not None:
                    signal = self._check_opportunity(market_id, yes_ask, no_ask)
                    if signal:
                        self.bus.publish("trade:signal", CONSUMER_ID, signal)
                        self.audit.log_event("trade:signal", CONSUMER_ID, signal)
                        signals.append(signal)

            self.bus.ack(CONSUMER_ID, evt["event_id"])

        return signals
