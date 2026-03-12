"""
POLY_LATENCY_ARB — Binance-to-Polymarket latency arbitrage strategy.

Exploits the repricing lag between Binance and Polymarket: when Binance data
implies a probability for a binary-outcome market and Polymarket has not yet
priced it in, a brief edge window opens.

Consumes:
  signal:binance_score  — Binance-derived implied probability for a Polymarket
                          binary market, with confidence and source asset.
  feed:price_update     — Current Polymarket YES/NO ask prices.

Emits:
  trade:signal          — BUY_YES when binance_implied_prob - yes_ask > EDGE_THRESHOLD
                        — BUY_NO  when (1 - binance_implied_prob) - no_ask > EDGE_THRESHOLD

Expected signal:binance_score payload:
  {
    "market_id":          str,    # linked Polymarket market identifier
    "implied_probability": float, # 0.0–1.0 YES probability implied by Binance
    "confidence":          float, # 0.0–1.0 confidence in the implied probability
    "source_asset":        str,   # "BTC" | "ETH" — Binance asset used
    "binance_price":       float, # Binance spot price at scoring time
    "price_change_pct":    float, # % price change that triggered this signal
  }

This module contains ONLY signal logic. No execution, no order routing.
"""

from core.poly_audit_log import PolyAuditLog
from core.poly_event_bus import PolyEventBus


CONSUMER_ID = "POLY_LATENCY_ARB"
ACCOUNT_ID  = "ACC_POLY_LATENCY_ARB"
PLATFORM    = "polymarket"

# Strategy parameters (matches POLY_STRATEGY_REGISTRY v1.2)
EDGE_THRESHOLD     = 0.10   # min edge (implied_prob - ask) to emit a signal
MIN_CONFIDENCE     = 0.70   # min Binance score confidence to consider
SUGGESTED_SIZE_EUR = 28.0   # suggested order size before Kelly sizing


class PolyLatencyArb:
    """Latency arbitrage strategy: exploits Binance-to-Polymarket repricing lag.

    Maintains in-memory caches of the latest Binance score and Polymarket price
    per market_id. A signal is emitted on each fresh binance_score event when the
    implied edge exceeds EDGE_THRESHOLD and the confidence meets MIN_CONFIDENCE.
    """

    def __init__(self, base_path="state"):
        self.bus   = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        # In-memory caches keyed by market_id
        self._binance_scores = {}   # market_id → latest signal:binance_score payload
        self._price_cache    = {}   # market_id → latest feed:price_update payload

    def _check_opportunity(
        self,
        market_id: str,
        score_payload: dict,
        price_payload: dict,
    ):
        """Evaluate a Binance score against the current Polymarket ask.

        Pure function — no I/O, no side effects.

        Args:
            market_id:     Market identifier.
            score_payload: signal:binance_score payload dict.
            price_payload: feed:price_update payload dict.

        Returns:
            Signal payload dict if an edge is detected, else None.
        """
        implied_prob = score_payload.get("implied_probability")
        confidence   = score_payload.get("confidence", 0.0)

        if implied_prob is None:
            return None
        if confidence < MIN_CONFIDENCE:
            return None

        yes_ask = price_payload.get("yes_ask")
        no_ask  = price_payload.get("no_ask")

        if yes_ask is None or no_ask is None:
            return None

        edge_yes = implied_prob - yes_ask
        edge_no  = (1.0 - implied_prob) - no_ask

        if edge_yes > EDGE_THRESHOLD:
            direction = "BUY_YES"
            edge      = round(edge_yes, 6)
            ask_used  = yes_ask
        elif edge_no > EDGE_THRESHOLD:
            direction = "BUY_NO"
            edge      = round(edge_no, 6)
            ask_used  = no_ask
        else:
            return None

        return {
            "strategy":          CONSUMER_ID,
            "account_id":        ACCOUNT_ID,
            "market_id":         market_id,
            "platform":          PLATFORM,
            "direction":         direction,
            "confidence":        round(min(1.0, confidence), 6),
            "suggested_size_eur": SUGGESTED_SIZE_EUR,
            "signal_type":       "latency_arb",
            "signal_detail": {
                "implied_probability": implied_prob,
                "ask_used":            ask_used,
                "edge":                edge,
                "direction":           direction,
                "source_asset":        score_payload.get("source_asset"),
                "binance_price":       score_payload.get("binance_price"),
                "confidence":          confidence,
            },
        }

    def run_once(self) -> list:
        """Poll the bus for relevant events and emit signals for detected edges.

        Processing order:
        - feed:price_update events update the price cache (sorted by timestamp,
          so stale prices are overwritten by newer ones).
        - signal:binance_score events trigger opportunity checks against the cache.
        - All events are acked regardless of outcome.

        Returns:
            List of signal payload dicts that were published to the bus.
        """
        events = self.bus.poll(
            CONSUMER_ID,
            topics=["signal:binance_score", "feed:price_update"],
        )

        signals = []

        for evt in events:
            topic   = evt["topic"]
            payload = evt["payload"]

            if topic == "feed:price_update":
                mid = payload.get("market_id")
                if mid:
                    self._price_cache[mid] = payload

            elif topic == "signal:binance_score":
                mid = payload.get("market_id")
                if mid:
                    self._binance_scores[mid] = payload
                    price_data = self._price_cache.get(mid)
                    if price_data is not None:
                        signal = self._check_opportunity(mid, payload, price_data)
                        if signal:
                            self.bus.publish("trade:signal", CONSUMER_ID, signal)
                            self.audit.log_event("trade:signal", CONSUMER_ID, signal)
                            signals.append(signal)

            self.bus.ack(CONSUMER_ID, evt["event_id"])

        return signals
