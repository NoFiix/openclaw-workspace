"""
POLY_CONVERGENCE_STRAT — Smart-money wallet convergence strategy.

Detects when 3+ high-EV wallets converge on the same direction (YES or NO)
for a given market, and cross-checks with the parsed resolution condition to
filter ambiguous criteria.  Emits BUY_YES or BUY_NO trade signals accordingly.

Strategy logic:
  1. Receive signal:wallet_convergence (3+ wallets agree on direction) from
     POLY_WALLET_TRACKER.
  2. Require signal:resolution_parsed to be cached for the same market
     (quality gate: rejects ambiguous resolution criteria).
  3. Emit trade:signal when:
       - wallet_count >= MIN_WALLET_COUNT (3 — enough consensus)
       - avg_ev_score >= MIN_EV_SCORE (0.55 — wallets bought at a meaningful
         discount; avg_ev_score = 1 − avg_entry_price per wallet tracker)
       - ambiguity_score < MAX_AMBIGUITY_SCORE (4 — clear resolution condition)

No LLM calls — pure deterministic logic.
No price feed needed — avg_ev_score already encodes price information.

Consumes:
  signal:wallet_convergence — convergent wallet group + direction (queue mode)
  signal:resolution_parsed  — boolean condition + quality scores (cache mode)

Emits:
  trade:signal — BUY_YES or BUY_NO (follows wallet consensus direction)

This module contains ONLY signal logic.  No execution, no order routing.
"""

from core.poly_audit_log import PolyAuditLog
from core.poly_event_bus import PolyEventBus


CONSUMER_ID         = "POLY_CONVERGENCE_STRAT"
ACCOUNT_ID          = "ACC_POLY_CONVERGENCE_STRAT"
PLATFORM            = "polymarket"

# Strategy parameters
MIN_WALLET_COUNT    = 3       # minimum convergent wallets to emit a signal
MIN_EV_SCORE        = 0.55    # minimum avg_ev_score (proxy for entry price edge)
MAX_AMBIGUITY_SCORE = 4       # reject markets with ambiguity_score >= this
SUGGESTED_SIZE_EUR  = 22.0


class PolyConvergenceStrat:
    """Wallet-convergence directional signal strategy.

    Accumulates resolution criteria from signal:resolution_parsed events and
    wallet convergence groups from signal:wallet_convergence events.  On each
    fresh convergence signal the market is evaluated against both caches and a
    trade signal is emitted when all filters pass.
    """

    def __init__(self, base_path="state"):
        self.bus   = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)

        # In-memory caches keyed by market_id
        self._resolution_cache  = {}   # market_id → signal:resolution_parsed payload
        self._convergence_cache = {}   # market_id → latest signal:wallet_convergence payload

    # ------------------------------------------------------------------
    # Pure opportunity check
    # ------------------------------------------------------------------

    def _check_opportunity(
        self,
        market_id: str,
        convergence_payload: dict,
        resolution_payload: dict,
    ):
        """Evaluate a market for a wallet-convergence trade opportunity.

        Args:
            market_id:           Market identifier.
            convergence_payload: signal:wallet_convergence payload dict.
            resolution_payload:  signal:resolution_parsed payload dict.

        Returns:
            Signal payload dict if an opportunity is detected, else None.
        """
        wallet_count = convergence_payload.get("wallet_count", 0)
        if wallet_count < MIN_WALLET_COUNT:
            return None

        avg_ev_score = convergence_payload.get("avg_ev_score", 0.0)
        if avg_ev_score < MIN_EV_SCORE:
            return None

        if resolution_payload.get("ambiguity_score", 10) >= MAX_AMBIGUITY_SCORE:
            return None

        raw_direction = convergence_payload.get("direction", "YES")
        direction     = "BUY_" + raw_direction  # "BUY_YES" or "BUY_NO"

        confidence = round(min(1.0, avg_ev_score * (wallet_count / MIN_WALLET_COUNT)), 6)

        return {
            "strategy":           CONSUMER_ID,
            "account_id":         ACCOUNT_ID,
            "market_id":          market_id,
            "platform":           PLATFORM,
            "direction":          direction,
            "confidence":         confidence,
            "suggested_size_eur": SUGGESTED_SIZE_EUR,
            "signal_type":        "convergence",
            "signal_detail": {
                "boolean_condition":     resolution_payload.get("boolean_condition"),
                "wallet_count":          wallet_count,
                "avg_ev_score":          round(avg_ev_score, 6),
                "convergent_wallets":    convergence_payload.get("convergent_wallets"),
                "ambiguity_score":       resolution_payload.get("ambiguity_score"),
                "unexpected_risk_score": resolution_payload.get("unexpected_risk_score"),
                "detection_timestamp":   convergence_payload.get("detection_timestamp"),
            },
        }

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_once(self) -> list:
        """Poll the bus, update caches, emit signals for fresh convergence events.

        Processing order:
        - signal:resolution_parsed events update the resolution cache (no trigger).
        - signal:wallet_convergence events update the convergence cache and mark
          the market as needing evaluation.
        - After all events are processed, each updated market is evaluated.
        - All events are acked regardless of outcome.

        Returns:
            List of trade:signal payload dicts published to the bus.
        """
        events = self.bus.poll(
            CONSUMER_ID,
            topics=["signal:wallet_convergence", "signal:resolution_parsed"],
        )

        updated_markets = set()

        for evt in events:
            topic   = evt["topic"]
            payload = evt["payload"]

            if topic == "signal:resolution_parsed":
                mid = payload.get("market_id")
                if mid:
                    self._resolution_cache[mid] = payload

            elif topic == "signal:wallet_convergence":
                mid = payload.get("market_id")
                if mid:
                    self._convergence_cache[mid] = payload
                    updated_markets.add(mid)

            self.bus.ack(CONSUMER_ID, evt["event_id"])

        signals = []
        for mid in updated_markets:
            convergence = self._convergence_cache.get(mid)
            resolution  = self._resolution_cache.get(mid)
            if convergence and resolution:
                signal = self._check_opportunity(mid, convergence, resolution)
                if signal:
                    self.bus.publish("trade:signal", CONSUMER_ID, signal)
                    self.audit.log_event("trade:signal", CONSUMER_ID, signal)
                    signals.append(signal)

        return signals
