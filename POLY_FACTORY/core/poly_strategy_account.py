"""
POLY_STRATEGY_ACCOUNT — Isolated capital account for a single strategy.

Tracks current capital, P&L, drawdown, and lifecycle status.
Complementary to POLY_STRATEGY_REGISTRY which tracks logical identity.

One instance = one file at state/accounts/ACC_POLY_{STRATEGY}.json.
Kill switch thresholds: -5% daily drawdown, -30% total drawdown.
"""

import copy
import threading
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore


ACCOUNTS_DIR = "accounts"
ARCHIVE_DIR = "accounts/archive"
INITIAL_CAPITAL = 1000.0
DAILY_DRAWDOWN_LIMIT_PCT = -5.0
TOTAL_DRAWDOWN_LIMIT_PCT = -30.0

VALID_STATUSES = {"paper_testing", "awaiting_human", "active", "paused", "stopped"}


class PolyStrategyAccount:
    """Isolated capital account for one strategy.

    Persists to state/accounts/ACC_POLY_{STRATEGY}.json.
    Use `create()` to initialise a new account, `load()` to restore from disk.
    """

    def __init__(self, data: dict, store: PolyDataStore, audit: PolyAuditLog):
        self._data = data
        self.store = store
        self.audit = audit
        self._lock = threading.Lock()
        self._rel_path = f"{ACCOUNTS_DIR}/{data['account_id']}.json"

    # ------------------------------------------------------------------
    # Class methods
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, strategy: str, platform: str,
               base_path: str = "state",
               initial_capital: float = INITIAL_CAPITAL) -> "PolyStrategyAccount":
        """Create and persist a new strategy account.

        Args:
            strategy: Strategy name (e.g. "POLY_ARB_SCANNER").
            platform: Target platform (e.g. "polymarket").
            base_path: Base path for state files.
            initial_capital: Starting capital in EUR (default 1,000€).

        Returns:
            A new PolyStrategyAccount instance.

        Raises:
            ValueError: If an account for this strategy already exists.
        """
        store = PolyDataStore(base_path=base_path)
        audit = PolyAuditLog(base_path=base_path)

        account_id = f"ACC_{strategy}"
        rel_path = f"{ACCOUNTS_DIR}/{account_id}.json"

        if store.exists(rel_path):
            raise ValueError(f"Account '{account_id}' already exists at {rel_path}")

        now = cls._static_now()
        data = {
            "account_id": account_id,
            "strategy": strategy,
            "status": "paper_testing",
            "platform": platform,
            "capital": {
                "initial": initial_capital,
                "current": initial_capital,
                "available": initial_capital,
            },
            "pnl": {
                "total": 0.0,
                "daily": 0.0,
                "session": 0.0,
            },
            "drawdown": {
                "high_water_mark": initial_capital,
                "current_drawdown_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "daily_pnl_pct": 0.0,
            },
            "performance": {
                "total_trades": 0,
                "paper_started": now,
                "last_trade_at": None,
            },
            "limits": {
                "daily_drawdown_limit_pct": DAILY_DRAWDOWN_LIMIT_PCT,
                "total_drawdown_limit_pct": TOTAL_DRAWDOWN_LIMIT_PCT,
            },
            "status_history": [
                {"status": "paper_testing", "timestamp": now}
            ],
            "created_at": now,
            "updated_at": now,
        }

        store.write_json(rel_path, data)

        audit.log_event(
            topic="account:created",
            producer="POLY_STRATEGY_ACCOUNT",
            payload={"account_id": account_id, "strategy": strategy,
                     "platform": platform, "initial_capital": initial_capital},
        )

        return cls(data, store, audit)

    @classmethod
    def load(cls, account_id: str, base_path: str = "state") -> "PolyStrategyAccount":
        """Load an existing account from disk.

        Args:
            account_id: Full account ID (e.g. "ACC_POLY_ARB_SCANNER").
            base_path: Base path for state files.

        Returns:
            A PolyStrategyAccount instance populated from disk.

        Raises:
            FileNotFoundError: If no account file is found.
        """
        store = PolyDataStore(base_path=base_path)
        audit = PolyAuditLog(base_path=base_path)

        rel_path = f"{ACCOUNTS_DIR}/{account_id}.json"
        data = store.read_json(rel_path)
        if data is None:
            raise FileNotFoundError(f"Account '{account_id}' not found at {rel_path}")

        return cls(data, store, audit)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def account_id(self) -> str:
        return self._data["account_id"]

    @property
    def strategy(self) -> str:
        return self._data["strategy"]

    @property
    def status(self) -> str:
        return self._data["status"]

    @property
    def data(self) -> dict:
        """Return a deep copy of the current account data."""
        with self._lock:
            return copy.deepcopy(self._data)

    # ------------------------------------------------------------------
    # Instance methods
    # ------------------------------------------------------------------

    def record_trade(self, pnl: float) -> dict:
        """Record a closed trade and update all capital/P&L/drawdown fields.

        Args:
            pnl: Trade P&L in EUR (positive = profit, negative = loss).

        Returns:
            Deep copy of updated account data.
        """
        with self._lock:
            d = self._data
            now = self._now()

            # Capital
            d["capital"]["current"] += pnl
            d["capital"]["available"] += pnl
            current = d["capital"]["current"]

            # P&L
            d["pnl"]["total"] += pnl
            d["pnl"]["daily"] += pnl
            d["pnl"]["session"] += pnl

            # Performance
            d["performance"]["total_trades"] += 1
            d["performance"]["last_trade_at"] = now

            # High water mark
            hwm = d["drawdown"]["high_water_mark"]
            if current > hwm:
                hwm = current
                d["drawdown"]["high_water_mark"] = hwm

            # Drawdown percentages
            current_dd_pct = ((current - hwm) / hwm * 100.0) if hwm > 0 else 0.0
            d["drawdown"]["current_drawdown_pct"] = current_dd_pct
            if current_dd_pct < d["drawdown"]["max_drawdown_pct"]:
                d["drawdown"]["max_drawdown_pct"] = current_dd_pct

            initial = d["capital"]["initial"]
            d["drawdown"]["daily_pnl_pct"] = (
                (d["pnl"]["daily"] / initial * 100.0) if initial > 0 else 0.0
            )

            d["updated_at"] = now
            self._save()
            result = copy.deepcopy(d)

        self.audit.log_event(
            topic="account:trade_recorded",
            producer="POLY_STRATEGY_ACCOUNT",
            payload={"account_id": self.account_id, "pnl": pnl,
                     "current_capital": result["capital"]["current"]},
        )

        return result

    def update_status(self, new_status: str) -> dict:
        """Change the account status and append to history.

        If new_status == "stopped", the account file is archived.

        Args:
            new_status: One of VALID_STATUSES.

        Returns:
            Deep copy of updated account data.

        Raises:
            ValueError: If new_status is not in VALID_STATUSES.
        """
        if new_status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{new_status}'. Must be one of {VALID_STATUSES}"
            )

        with self._lock:
            d = self._data
            now = self._now()
            d["status"] = new_status
            d["status_history"].append({"status": new_status, "timestamp": now})
            d["updated_at"] = now
            self._save()
            result = copy.deepcopy(d)

        self.audit.log_event(
            topic="account:status_updated",
            producer="POLY_STRATEGY_ACCOUNT",
            payload={"account_id": self.account_id, "new_status": new_status},
        )

        if new_status == "stopped":
            self.archive()

        return result

    def reset_daily(self) -> None:
        """Reset daily P&L and daily drawdown percentage. Called nightly by Orchestrator."""
        with self._lock:
            self._data["pnl"]["daily"] = 0.0
            self._data["drawdown"]["daily_pnl_pct"] = 0.0
            self._data["updated_at"] = self._now()
            self._save()

    def archive(self) -> str:
        """Move the account file to the archive directory.

        Returns:
            Destination path of the archived file.
        """
        return self.store.archive(self._rel_path, ARCHIVE_DIR)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Persist the current data to disk. Caller must hold _lock."""
        self.store.write_json(self._rel_path, self._data)

    def _now(self) -> str:
        return self._static_now()

    @staticmethod
    def _static_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
