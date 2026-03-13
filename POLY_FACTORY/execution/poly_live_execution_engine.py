"""
POLY_LIVE_EXECUTION_ENGINE — Real on-chain execution engine for POLY_FACTORY.

Submits orders to Polymarket via py-clob-client. Credentials are read exclusively
from environment variables (POLYMARKET_API_KEY, POLYMARKET_API_SECRET, WALLET_PRIVATE_KEY).
Retries up to MAX_RETRIES times on transient errors, then abandons with audit log.

SEPARATION: This module is SEPARATE from poly_paper_execution_engine.py.
The paper engine cannot import this file. This file never simulates — it always
executes for real when deployed.
"""

import os
import time
import threading
from datetime import datetime, timezone

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_audit_log import PolyAuditLog
from core.poly_strategy_account import PolyStrategyAccount


CONSUMER_ID     = "POLY_LIVE_EXECUTION_ENGINE"
FEE_RATE        = 0.002   # 0.2% Polymarket CLOB fee
MAX_RETRIES     = 3
RETRY_DELAY_S   = 1.0
ORDER_TIMEOUT_S = 30
LIVE_TRADES_LOG = "trading/live_trades_log.jsonl"

# Maps trade direction to CLOB side(s). BUY_YES_AND_NO submits two sub-orders.
SIDES_MAP = {
    "BUY_YES":        ["YES"],
    "BUY_NO":         ["NO"],
    "BUY_YES_AND_NO": ["YES", "NO"],
}

DEFAULT_PRICE_LIMIT = 0.99


class PolyLiveExecutionEngine:
    """Submits live orders on-chain via an injectable CLOB client.

    Injectable client interface (duck-typed):
        client.place_order(market_id, side, size_eur, price_limit) -> {
            "tx_hash":    str,
            "fill_price": float,
            "gas_cost":   float,
        }

    If clob_client=None the real py-clob-client is loaded lazily on first call,
    using credentials from environment variables.
    """

    def __init__(self, base_path="state", clob_client=None):
        self.base_path = base_path
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self._clob_client = clob_client
        self._lock = threading.Lock()
        self._id_counter = 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_trade_id(self) -> str:
        """Thread-safe trade ID: TRD_{YYYYMMDD}_{counter:04d}."""
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        with self._lock:
            self._id_counter += 1
            counter = self._id_counter
        return f"TRD_{date_str}_{counter:04d}"

    def _get_clob_client(self):
        """Return the active CLOB client, loading the real one if none was injected."""
        if self._clob_client is not None:
            return self._clob_client

        # Lazy-load real py-clob-client — only reached in production
        from py_clob_client.client import ClobClient  # noqa: PLC0415

        api_key    = os.environ["POLYMARKET_API_KEY"]
        api_secret = os.environ["POLYMARKET_API_SECRET"]
        private_key = os.environ["WALLET_PRIVATE_KEY"]

        self._clob_client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
            creds={
                "apiKey":    api_key,
                "secret":    api_secret,
                "passphrase": "",
            },
        )
        return self._clob_client

    def _place_order(self, market_id: str, side: str,
                     size_eur: float, price_limit: float) -> dict:
        """Submit a single order. Raises on any error."""
        client = self._get_clob_client()
        start = time.time()
        result = client.place_order(
            market_id=market_id,
            side=side,
            size_eur=size_eur,
            price_limit=price_limit,
        )
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "tx_hash":          result["tx_hash"],
            "fill_price":       float(result["fill_price"]),
            "gas_cost":         float(result.get("gas_cost", 0.0)),
            "execution_time_ms": elapsed_ms,
        }

    def _place_with_retry(self, market_id: str, side: str,
                          size_eur: float, price_limit: float) -> dict:
        """Submit with up to MAX_RETRIES attempts. Re-raises after exhausting retries."""
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return self._place_order(market_id, side, size_eur, price_limit)
            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_S)
        raise last_error  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, payload: dict) -> dict | None:
        """Execute a live order from an execute:live payload.

        Args:
            payload: Dict matching the execute:live payload schema.

        Returns:
            trade:live_executed payload dict on success, None on failure.
        """
        strategy          = payload["strategy"]
        account_id        = payload["account_id"]
        market_id         = payload["market_id"]
        platform          = payload["platform"]
        direction         = payload["direction"]
        size_eur          = float(payload["size_eur"])
        slippage_estimated = float(payload.get("slippage_estimated") or 0.0)
        tranches          = payload.get("tranches", [])

        sides = SIDES_MAP.get(direction, ["YES"])
        n     = len(sides)
        sub_size = size_eur / n

        trade_id = self._generate_trade_id()

        # --- Submit one order per side ---
        sub_results = []
        for i, side in enumerate(sides):
            price_limit = (
                tranches[i]["price_limit"] if i < len(tranches) else DEFAULT_PRICE_LIMIT
            )
            try:
                r = self._place_with_retry(market_id, side, sub_size, price_limit)
                r["side"]       = side
                r["sub_size"]   = sub_size
                r["price_limit"] = price_limit
                r["fees"]       = sub_size * FEE_RATE
                sub_results.append(r)
            except Exception as exc:
                self.audit.log_event(
                    topic="trade:live_failed",
                    producer=CONSUMER_ID,
                    payload={
                        "trade_id":  trade_id,
                        "strategy":  strategy,
                        "market_id": market_id,
                        "side":      side,
                        "error":     str(exc),
                        "retries":   MAX_RETRIES,
                    },
                )
                return None

        # --- Combine sub-order results ---
        total_gas  = sum(r["gas_cost"] for r in sub_results)
        total_fees = sum(r["fees"]     for r in sub_results)
        total_time = sum(r["execution_time_ms"] for r in sub_results)

        # Weighted-average fill price
        fill_price = sum(r["fill_price"] * r["sub_size"] for r in sub_results) / size_eur

        # Price limit of first side (representative)
        first_limit = sub_results[0]["price_limit"]
        slippage_actual = max(0.0, fill_price - first_limit + slippage_estimated)

        tx_hash = ",".join(r["tx_hash"] for r in sub_results)

        result = {
            "trade_id":         trade_id,
            "execution_mode":   "live",
            "strategy":         strategy,
            "account_id":       account_id,
            "market_id":        market_id,
            "platform":         platform,
            "direction":        direction,
            "fill_price":       round(fill_price, 6),
            "slippage_actual":  round(slippage_actual, 6),
            "size_eur":         size_eur,
            "fees":             round(total_fees, 6),
            "gas_cost":         round(total_gas, 6),
            "tx_hash":          tx_hash,
            "execution_time_ms": total_time,
        }

        # Debit the strategy account
        account = PolyStrategyAccount.load(account_id, self.base_path)
        account.record_trade(-(size_eur + total_fees))

        # Persist trade log
        self.store.append_jsonl(LIVE_TRADES_LOG, result)

        # Publish bus event
        self.bus.publish(
            topic="trade:live_executed",
            producer=CONSUMER_ID,
            payload=result,
        )

        # Audit
        self.audit.log_event(
            topic="trade:live_executed",
            producer=CONSUMER_ID,
            payload=result,
        )

        return result

    def run_once(self) -> list:
        """Poll execute:live events and process each one.

        Returns:
            List of execute results (dict or None per event).
        """
        events = self.bus.poll(CONSUMER_ID, topics=["execute:live"])
        results = []
        for evt in events:
            result = self.execute(evt["payload"])
            self.bus.ack(CONSUMER_ID, evt["event_id"])
            results.append(result)
        return results
