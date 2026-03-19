"""
POLY_PAPER_EXECUTION_ENGINE — Paper trading execution simulator for POLY_FACTORY.

Simulates trade execution with realistic fill prices, slippage from market structure,
and fee calculation. Debits the strategy account and emits a trade:paper_executed bus event.

SAFETY: This module must not import the clob client library, access wallets, or send transactions.
It is physically incapable of sending real orders.
"""

import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("POLY_PAPER_EXECUTION_ENGINE")

from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_audit_log import PolyAuditLog
from core.poly_strategy_account import PolyStrategyAccount
from risk.poly_risk_guardian import PolyRiskGuardian


CONSUMER_ID = "POLY_PAPER_EXECUTION_ENGINE"
FEE_RATE = 0.002  # 0.2% of trade size
PAPER_TRADES_LOG = "trading/paper_trades_log.jsonl"
PNL_LOG_DIR      = "trading/positions_by_strategy"
MARKET_STRUCTURE_FILE = "feeds/market_structure.json"


class PolyPaperExecutionEngine:
    """Simulates paper trade execution with slippage, fees, and account debiting."""

    def __init__(self, base_path="state", risk_guardian=None):
        self.base_path = base_path
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self.risk_guardian = risk_guardian or PolyRiskGuardian(base_path=base_path)
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

    def _get_slippage(self, market_id: str, size_eur: float, slippage_estimated: float) -> float:
        """Compute slippage from market structure depth for the actual trade size.

        Falls back to slippage_estimated when the market has no structure data.

        Args:
            market_id: Market identifier.
            size_eur: Actual trade size in EUR (used as order size proxy).
            slippage_estimated: Fallback slippage from the signal payload.

        Returns:
            Slippage as a float.
        """
        market_structure = self.store.read_json(MARKET_STRUCTURE_FILE)
        if market_structure and market_id in market_structure:
            struct = market_structure[market_id]
            depth_usd = struct.get("depth_usd", 0)
            spread_bps = struct.get("spread_bps", 0)
            if depth_usd > 0:
                return (spread_bps / 10_000 / 2) + size_eur / max(depth_usd, size_eur)
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

        # Capital check: reject if available capital is insufficient
        account_pre = PolyStrategyAccount.load(account_id, self.base_path)
        available = account_pre.data["capital"]["available"]
        required = size_eur + size_eur * FEE_RATE
        if available < required:
            logger.info(
                "REJECTED: insufficient capital | strategy=%s | available=%.2f | required=%.2f | market=%s",
                strategy, available, required, market_id,
            )
            return None

        slippage_actual = self._get_slippage(market_id, size_eur, slippage_estimated)
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

        # Register open position in risk guardian for position tracking
        category = payload.get("signal_type", payload.get("category", "unknown"))
        self.risk_guardian.add_position(strategy, market_id, size_eur, category)

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
            if result is not None:
                results.append(result)
        return results
