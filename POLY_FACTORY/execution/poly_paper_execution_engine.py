"""
POLY_PAPER_EXECUTION_ENGINE — Paper trading execution simulator for POLY_FACTORY.

Simulates trade execution with realistic fill prices, slippage from market structure,
and fee calculation. Debits the strategy account and emits a trade:paper_executed bus event.

SAFETY: This module must not import the clob client library, access wallets, or send transactions.
It is physically incapable of sending real orders.
"""

import threading
from datetime import datetime, timezone

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_audit_log import PolyAuditLog
from core.poly_strategy_account import PolyStrategyAccount


CONSUMER_ID = "POLY_PAPER_EXECUTION_ENGINE"
FEE_RATE = 0.002  # 0.2% of trade size
PAPER_TRADES_LOG = "trading/paper_trades_log.jsonl"
PNL_LOG_DIR      = "trading/positions_by_strategy"
MARKET_STRUCTURE_FILE = "feeds/market_structure.json"


class PolyPaperExecutionEngine:
    """Simulates paper trade execution with slippage, fees, and account debiting."""

    def __init__(self, base_path="state"):
        self.base_path = base_path
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self._lock = threading.Lock()
        self._id_counter = 0

    def _generate_trade_id(self) -> str:
        """Thread-safe trade ID generation: TRD_{YYYYMMDD}_{counter:04d}."""
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        with self._lock:
            self._id_counter += 1
            counter = self._id_counter
        return f"TRD_{date_str}_{counter:04d}"

    def _get_slippage(self, market_id: str, slippage_estimated: float) -> float:
        """Return actual slippage from market structure, or fall back to estimate.

        Args:
            market_id: Market identifier.
            slippage_estimated: Fallback slippage from the signal payload.

        Returns:
            Slippage as a float.
        """
        market_structure = self.store.read_json(MARKET_STRUCTURE_FILE)
        if market_structure and market_id in market_structure:
            return market_structure[market_id].get("slippage_1k", slippage_estimated)
        return slippage_estimated

    def execute(self, payload: dict) -> dict:
        """Execute a paper trade from an execute:paper payload.

        Args:
            payload: Dict matching the execute:paper payload schema.

        Returns:
            Dict matching the trade:paper_executed payload schema.
        """
        strategy = payload["strategy"]
        account_id = payload["account_id"]
        market_id = payload["market_id"]
        platform = payload["platform"]
        direction = payload["direction"]
        size_eur = float(payload["size_eur"])
        expected_fill_price = float(payload["expected_fill_price"])
        slippage_estimated = float(payload["slippage_estimated"])

        slippage_actual = self._get_slippage(market_id, slippage_estimated)
        fill_price = min(expected_fill_price + slippage_actual, 0.99)
        fees = size_eur * FEE_RATE

        trade_id = self._generate_trade_id()

        result = {
            "trade_id": trade_id,
            "execution_mode": "paper",
            "strategy": strategy,
            "account_id": account_id,
            "market_id": market_id,
            "platform": platform,
            "direction": direction,
            "fill_price": fill_price,
            "slippage_actual": slippage_actual,
            "size_eur": size_eur,
            "fees": fees,
            "gas_cost": 0.0,
            "tx_hash": None,
            "execution_time_ms": 0,
        }

        # Debit account: capital cost = size + fees (negative P&L = capital spent)
        account = PolyStrategyAccount.load(account_id, self.base_path)
        account.record_trade(-(size_eur + fees))

        # Persist trade log
        self.store.append_jsonl(PAPER_TRADES_LOG, result)

        # Publish bus event
        self.bus.publish(
            topic="trade:paper_executed",
            producer=CONSUMER_ID,
            payload=result,
        )

        # Audit
        self.audit.log_event(
            topic="trade:paper_executed",
            producer=CONSUMER_ID,
            payload=result,
        )

        # Decay detector feed — one JSONL record per closed paper trade
        pnl_record = {
            "trade_id":  trade_id,
            "strategy":  strategy,
            "market_id": market_id,
            "direction": direction,
            "size_eur":  size_eur,
            "pnl":       -(size_eur + fees),  # capital cost at execution (paper position opened)
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.store.append_jsonl(f"{PNL_LOG_DIR}/{strategy}_pnl.jsonl", pnl_record)

        return result

    def run_once(self) -> list:
        """Poll execute:paper events and process each one.

        Returns:
            List of trade result dicts.
        """
        events = self.bus.poll(CONSUMER_ID, topics=["execute:paper"])
        results = []
        for evt in events:
            result = self.execute(evt["payload"])
            self.bus.ack(CONSUMER_ID, evt["event_id"])
            results.append(result)
        return results
