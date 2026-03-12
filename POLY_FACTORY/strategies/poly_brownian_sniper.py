"""
POLY_BROWNIAN_SNIPER — Geometric Brownian Motion binary-market probability strategy.

Uses the GBM model to estimate the fair probability that a Binance-tracked asset
(BTC, ETH) will exceed a binary-market strike price by resolution date.  When the
GBM-implied probability significantly exceeds the Polymarket YES ask, the market is
mispriced and a BUY_YES signal is emitted.

GBM formula (risk-neutral, zero drift):
  P(S(T) > K) = N(d2)
  d2 = ( ln(S0/K) - 0.5 * σ² * T ) / ( σ * √T )

where:
  S0   = current Binance price
  K    = strike price (binary event threshold)
  T    = time to resolution in years
  σ    = annualised volatility estimated from the rolling 60-second price history
  N(·) = standard normal CDF

Consumes:
  signal:binance_score  — provides S0, K, days_to_resolution, confidence.
                          Also drives price-history accumulation (one price per event).
  feed:price_update     — provides the current Polymarket YES ask price.

Emits:
  trade:signal          — BUY_YES when gbm_prob - yes_ask > EDGE_THRESHOLD.

Expected signal:binance_score payload:
  {
    "market_id":          str,   # linked Polymarket market
    "symbol":             str,   # Binance asset (overwrite-mode dedup key)
    "current_price":      float, # S0 — current Binance spot price
    "strike_price":       float, # K  — binary-event threshold price
    "days_to_resolution": float, # T in days until market closes
    "confidence":         float, # 0.0–1.0 data-quality score
  }

This module contains ONLY signal logic.  No execution, no order routing.
"""

import math
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_event_bus import PolyEventBus


CONSUMER_ID = "POLY_BROWNIAN_SNIPER"
ACCOUNT_ID  = "ACC_POLY_BROWNIAN_SNIPER"
PLATFORM    = "polymarket"

# Strategy parameters (matches POLY_STRATEGY_REGISTRY v1.2)
EDGE_THRESHOLD     = 0.08   # min (gbm_prob - yes_ask) to emit a signal
MIN_CONFIDENCE     = 0.65   # minimum Binance score confidence to consider
MIN_PRICE_HISTORY  = 5      # minimum price samples required for σ estimation
WINDOW_SECONDS     = 60     # rolling price-history window in seconds
SUGGESTED_SIZE_EUR = 25.0   # suggested order size before Kelly sizing

# Annualise log-return std assuming ~1 observation per minute:
#   σ_annual = σ_per_obs * sqrt(252 trading days * 24 hours * 60 minutes)
ANNUALIZATION_FACTOR = 252 * 24 * 60  # 362 880 observations per year


# ---------------------------------------------------------------------------
# Pure mathematical helpers
# ---------------------------------------------------------------------------

def _normal_cdf(x: float) -> float:
    """Standard normal CDF via the complementary error function.

    Accurate to machine precision using Python's built-in math.erfc.
    """
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _compute_volatility(prices: list) -> float:
    """Annualised volatility σ from a sequence of asset prices.

    Uses the sample standard deviation of log returns, then annualises by
    ANNUALIZATION_FACTOR (treating each observation as 1 minute apart).

    Args:
        prices: Sequence of positive asset prices (oldest first).

    Returns:
        Annualised σ ≥ 0.  Returns 0.0 if fewer than 2 prices or zero variance.
    """
    n = len(prices)
    if n < 2:
        return 0.0

    log_returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, n)]
    m = len(log_returns)
    mean = sum(log_returns) / m
    variance = sum((r - mean) ** 2 for r in log_returns) / max(m - 1, 1)
    std = math.sqrt(variance)
    return std * math.sqrt(ANNUALIZATION_FACTOR)


def _gbm_probability(
    current_price: float,
    strike_price: float,
    sigma: float,
    days_to_resolution: float,
) -> float:
    """P(S(T) > K) under GBM with zero drift (risk-neutral binary call).

    Args:
        current_price:      S0 — current asset price.
        strike_price:       K  — binary-event threshold.
        sigma:              Annualised volatility.
        days_to_resolution: Days until the binary event resolves.

    Returns:
        Probability in [0, 1].  Returns 0.0 if any input is non-positive.
    """
    if current_price <= 0 or strike_price <= 0 or sigma <= 0 or days_to_resolution <= 0:
        return 0.0

    T  = days_to_resolution / 365.0
    d2 = (math.log(current_price / strike_price) - 0.5 * sigma ** 2 * T) / (
        sigma * math.sqrt(T)
    )
    return _normal_cdf(d2)


# ---------------------------------------------------------------------------
# Strategy class
# ---------------------------------------------------------------------------

class PolyBrownianSniper:
    """GBM-based binary prediction market strategy.

    Maintains a rolling 60-second price history derived from incoming
    signal:binance_score events.  On each fresh score event it estimates σ,
    computes the GBM fair probability, and compares to the cached Polymarket
    YES ask.  Signals are emitted when the edge exceeds EDGE_THRESHOLD.
    """

    def __init__(self, base_path="state"):
        self.bus   = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        # In-memory caches keyed by market_id
        self._price_cache    = {}   # market_id → latest feed:price_update payload
        self._score_cache    = {}   # market_id → latest signal:binance_score payload
        self._price_history  = {}   # market_id → [(unix_timestamp, asset_price)]

    # ------------------------------------------------------------------
    # Price-history helpers
    # ------------------------------------------------------------------

    def _update_price_history(
        self,
        market_id: str,
        price: float,
        timestamp_s: float = None,
    ) -> None:
        """Append a price observation and prune entries older than WINDOW_SECONDS.

        Args:
            market_id:   Market identifier.
            price:       Asset price to record.
            timestamp_s: Unix timestamp in seconds.  Defaults to now.
        """
        if timestamp_s is None:
            timestamp_s = datetime.now(timezone.utc).timestamp()

        history = self._price_history.setdefault(market_id, [])
        history.append((timestamp_s, price))

        cutoff = timestamp_s - WINDOW_SECONDS
        self._price_history[market_id] = [
            (t, p) for t, p in history if t >= cutoff
        ]

    def _get_recent_prices(self, market_id: str) -> list:
        """Return the list of price values in the rolling window for market_id."""
        return [p for _, p in self._price_history.get(market_id, [])]

    # ------------------------------------------------------------------
    # Pure opportunity check
    # ------------------------------------------------------------------

    def _check_opportunity(
        self,
        market_id: str,
        score_payload: dict,
        price_payload: dict,
        prices_60s: list,
    ):
        """Evaluate a Binance score against current Polymarket ask using GBM.

        Pure function — no I/O, no side effects.

        Args:
            market_id:     Market identifier.
            score_payload: signal:binance_score payload dict.
            price_payload: feed:price_update payload dict.
            prices_60s:    Rolling 60-second Binance price history (oldest first).

        Returns:
            Signal payload dict if an edge is detected, else None.
        """
        confidence = score_payload.get("confidence", 0.0)
        if confidence < MIN_CONFIDENCE:
            return None

        current_price      = score_payload.get("current_price")
        strike_price       = score_payload.get("strike_price")
        days_to_resolution = score_payload.get("days_to_resolution")

        if current_price is None or strike_price is None or days_to_resolution is None:
            return None
        if current_price <= 0 or strike_price <= 0 or days_to_resolution <= 0:
            return None

        if len(prices_60s) < MIN_PRICE_HISTORY:
            return None

        sigma = _compute_volatility(prices_60s)
        if sigma <= 0:
            return None

        gbm_prob = _gbm_probability(current_price, strike_price, sigma, days_to_resolution)

        yes_ask = price_payload.get("yes_ask")
        if yes_ask is None:
            return None

        edge = gbm_prob - yes_ask
        if edge <= EDGE_THRESHOLD:
            return None

        return {
            "strategy":          CONSUMER_ID,
            "account_id":        ACCOUNT_ID,
            "market_id":         market_id,
            "platform":          PLATFORM,
            "direction":         "BUY_YES",
            "confidence":        round(min(1.0, confidence), 6),
            "suggested_size_eur": SUGGESTED_SIZE_EUR,
            "signal_type":       "brownian_sniper",
            "signal_detail": {
                "gbm_probability":   round(gbm_prob, 6),
                "yes_ask":           yes_ask,
                "edge":              round(edge, 6),
                "sigma":             round(sigma, 6),
                "current_price":     current_price,
                "strike_price":      strike_price,
                "days_to_resolution": days_to_resolution,
            },
        }

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_once(self) -> list:
        """Poll the bus, update caches and history, emit signals.

        Processing order:
        - feed:price_update events update the Polymarket price cache.
        - signal:binance_score events update the score cache and price history,
          and mark the market as needing evaluation.
        - After all events are processed, each updated market is evaluated.
        - All events are acked regardless of outcome.

        Returns:
            List of trade:signal payload dicts published to the bus.
        """
        events = self.bus.poll(
            CONSUMER_ID,
            topics=["signal:binance_score", "feed:price_update"],
        )

        updated_markets = set()

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
                    self._score_cache[mid] = payload
                    cp = payload.get("current_price")
                    if cp:
                        self._update_price_history(mid, cp)
                    updated_markets.add(mid)

            self.bus.ack(CONSUMER_ID, evt["event_id"])

        signals = []
        for mid in updated_markets:
            score = self._score_cache.get(mid)
            price = self._price_cache.get(mid)
            if score and price:
                prices = self._get_recent_prices(mid)
                signal = self._check_opportunity(mid, score, price, prices)
                if signal:
                    self.bus.publish("trade:signal", CONSUMER_ID, signal)
                    self.audit.log_event("trade:signal", CONSUMER_ID, signal)
                    signals.append(signal)

        return signals
