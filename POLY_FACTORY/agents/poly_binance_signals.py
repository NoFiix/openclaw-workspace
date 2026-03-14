"""
POLY_BINANCE_SIGNALS — Transforms raw Binance feed data into trading signals.

Computes 4 signals (OBI, CVD, VWAP position, Momentum) and a composite score
in the range [-1, +1]. Publishes `signal:binance_score` per symbol.
Pure math, no external APIs. Target: < 50ms per tick.
"""

import collections
import logging
import math

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus

logger = logging.getLogger("POLY_BINANCE_SIGNALS")

STATE_FILE = "feeds/binance_signals.json"
BINANCE_RAW_FILE = "feeds/binance_raw.json"

EMA_5_ALPHA = 2 / 6
EMA_20_ALPHA = 2 / 21
VWAP_WINDOW_SIZE = 50
CVD_SCALE = 10_000.0
WEIGHTS = {"obi": 0.35, "cvd": 0.25, "vwap_position": 0.20, "momentum": 0.20}


class PolyBinanceSignals:
    """Transforms Binance feed ticks into composite trading signals."""

    def __init__(self, base_path="state", symbols=None):
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)

        # Per-symbol EMA state
        self._ema5 = {}
        self._ema20 = {}

        # Per-symbol CVD (running scalar)
        self._cvd = {}

        # Per-symbol previous price (for CVD direction)
        self._prev_price = {}

        # Per-symbol tick counter (for warmup)
        self._tick_count = {}

        # Per-symbol VWAP rolling window of (price, qty) tuples
        self._vwap_window = {}

        # Last published payload per symbol
        self._state_cache = {}

    # ------------------------------------------------------------------
    # Pure computation methods
    # ------------------------------------------------------------------

    def _compute_obi(self, bids, asks):
        """Compute Order Book Imbalance from top-5 bids and asks.

        Args:
            bids: List of [price, qty] or {"price": ..., "qty": ...} entries.
            asks: Same format.

        Returns:
            Float in [-1, +1]. 0.0 if book is empty.
        """
        def _sum_qty(levels):
            total = 0.0
            for level in levels:
                if isinstance(level, (list, tuple)):
                    total += float(level[1])
                else:
                    total += float(level.get("qty", 0))
            return total

        bid_qty = _sum_qty(bids)
        ask_qty = _sum_qty(asks)
        total = bid_qty + ask_qty
        if total == 0:
            return 0.0
        return (bid_qty - ask_qty) / total

    def _update_ema(self, current, price, alpha):
        """Single EMA step. Seeds with price if current is None.

        Args:
            current: Current EMA value or None.
            price: New price observation.
            alpha: Smoothing factor.

        Returns:
            New EMA value.
        """
        if current is None:
            return float(price)
        return current * (1 - alpha) + float(price) * alpha

    def _compute_momentum(self, symbol, price):
        """Update EMA5/EMA20 and return tanh-normalized momentum signal.

        Returns 0.0 during warmup (< 5 ticks).

        Args:
            symbol: Trading pair symbol.
            price: Current price.

        Returns:
            Float in [-1, +1].
        """
        tick = self._tick_count.get(symbol, 0)

        self._ema5[symbol] = self._update_ema(self._ema5.get(symbol), price, EMA_5_ALPHA)
        self._ema20[symbol] = self._update_ema(self._ema20.get(symbol), price, EMA_20_ALPHA)

        if tick < 5:
            return 0.0

        ema5 = self._ema5[symbol]
        ema20 = self._ema20[symbol]
        denom = max(ema20, 1e-9)
        return math.tanh((ema5 - ema20) / denom * 20)

    def _update_cvd(self, symbol, price, qty):
        """Infer trade direction from price change and accumulate CVD.

        Args:
            symbol: Trading pair symbol.
            price: Current price.
            qty: Trade quantity (last trade size).

        Returns:
            Raw CVD value (unbounded).
        """
        prev = self._prev_price.get(symbol)
        direction = 1 if (prev is None or price >= prev) else -1
        self._prev_price[symbol] = float(price)

        current_cvd = self._cvd.get(symbol, 0.0)
        new_cvd = current_cvd + direction * float(qty)
        self._cvd[symbol] = new_cvd
        return new_cvd

    def _compute_vwap_position(self, symbol, price, qty):
        """Append tick to VWAP window and return clipped vwap_position.

        Args:
            symbol: Trading pair symbol.
            price: Current price.
            qty: Trade quantity.

        Returns:
            Float in [-1, +1].
        """
        if symbol not in self._vwap_window:
            self._vwap_window[symbol] = collections.deque(maxlen=VWAP_WINDOW_SIZE)

        self._vwap_window[symbol].append((float(price), float(qty)))

        total_qty = sum(q for _, q in self._vwap_window[symbol])
        if total_qty == 0:
            return 0.0

        vwap = sum(p * q for p, q in self._vwap_window[symbol]) / total_qty
        denom = max(vwap, 1e-9)
        raw = (float(price) - vwap) / denom * 10
        return max(-1.0, min(1.0, raw))

    # ------------------------------------------------------------------
    # Pipeline methods
    # ------------------------------------------------------------------

    def _build_payload(self, symbol, price, obi, cvd, vwap_position, momentum):
        """Build the full signal payload including composite score.

        Args:
            symbol: Trading pair symbol.
            price: Current price.
            obi: Order Book Imbalance signal.
            cvd: Raw CVD value.
            vwap_position: VWAP position signal.
            momentum: EMA momentum signal.

        Returns:
            Dict with all 7 fields.
        """
        cvd_norm = math.tanh(cvd / CVD_SCALE)
        composite = (
            WEIGHTS["obi"] * obi
            + WEIGHTS["cvd"] * cvd_norm
            + WEIGHTS["vwap_position"] * vwap_position
            + WEIGHTS["momentum"] * momentum
        )
        composite_score = max(-1.0, min(1.0, composite))

        return {
            "symbol": symbol,
            "price": float(price),
            "obi": obi,
            "cvd": cvd,
            "vwap_position": vwap_position,
            "momentum": momentum,
            "composite_score": composite_score,
        }

    def process_tick(self, binance_payload):
        """Full signal computation pipeline for one Binance feed tick.

        Args:
            binance_payload: Dict from `feed:binance_update` payload.

        Returns:
            Signal payload dict ready for publishing.
        """
        symbol = binance_payload["symbol"]
        price = float(binance_payload["price"])
        qty = float(binance_payload.get("last_trade_qty", 0.0))
        bids = binance_payload.get("bids_top5", [])
        asks = binance_payload.get("asks_top5", [])

        # Increment tick counter before computing momentum
        self._tick_count[symbol] = self._tick_count.get(symbol, 0) + 1

        obi = self._compute_obi(bids, asks)
        cvd = self._update_cvd(symbol, price, qty)
        vwap_position = self._compute_vwap_position(symbol, price, qty)
        momentum = self._compute_momentum(symbol, price)

        return self._build_payload(symbol, price, obi, cvd, vwap_position, momentum)

    def update(self, symbol, payload):
        """Persist state and publish signal to the bus.

        Args:
            symbol: Trading pair symbol.
            payload: Signal payload dict from process_tick().
        """
        self._state_cache[symbol] = payload
        self.store.write_json(STATE_FILE, self._state_cache)
        self.bus.publish(
            topic="signal:binance_score",
            producer="POLY_BINANCE_SIGNALS",
            payload=payload,
            priority="normal",
        )

    def run_once(self):
        """Read binance_raw.json and compute signals for every known symbol.

        Reads directly from the feed's state file (written by PolyBinanceFeed)
        rather than bus polling, since OBI computation needs the current orderbook
        snapshot and bus overwrite mode only delivers the latest event.

        Returns:
            List of signal payload dicts computed this cycle.
        """
        raw = self.store.read_json(BINANCE_RAW_FILE) or {}
        results = []
        for symbol, payload in raw.items():
            try:
                signal = self.process_tick(payload)
                self.update(symbol, signal)
                results.append(signal)
            except Exception:
                logger.exception("Failed to process symbol %s", symbol)
        return results
