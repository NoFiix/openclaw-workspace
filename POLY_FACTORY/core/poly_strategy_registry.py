"""
POLY_STRATEGY_REGISTRY — Central registry of the logical lifecycle of strategies.

Tracks identity, version, parameters, platform, and lifecycle history for each strategy.
Complementary to POLY_STRATEGY_ACCOUNT which tracks capital.

Consumers: POLY_EXECUTION_ROUTER, POLY_FACTORY_ORCHESTRATOR,
           POLY_STRATEGY_PROMOTION_GATE, POLY_STRATEGY_EVALUATOR.
"""

import copy
import threading
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore


REGISTRY_PATH = "registry/strategy_registry.json"

VALID_STATUSES = {
    "scouted",
    "backtesting",
    "paper_testing",
    "awaiting_promotion",
    "live",
    "paused",
    "stopped",
}

# Maps a status to the lifecycle timestamp field that records when it was first entered.
STATUS_TO_LIFECYCLE = {
    "scouted":            "scouted",
    "backtesting":        "backtested",
    "paper_testing":      "paper_started",
    "awaiting_promotion": "paper_evaluated",
    "live":               "promoted_live",
    "paused":             "paused",
    "stopped":            "stopped",
}

_EMPTY_LIFECYCLE = {
    "scouted":        None,
    "backtested":     None,
    "paper_started":  None,
    "paper_evaluated": None,
    "promoted_live":  None,
    "paused":         None,
    "stopped":        None,
    "reactivated":    None,
}


class PolyStrategyRegistry:
    """Central registry of strategy identity, version, parameters, and lifecycle."""

    def __init__(self, base_path="state"):
        self.store = PolyDataStore(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self._lock = threading.Lock()
        self._data = {}
        self._id_counter = 0
        self._load()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self):
        """Load registry from disk into the in-memory cache."""
        data = self.store.read_json(REGISTRY_PATH)
        if data:
            self._data = data
            self._id_counter = len(data)

    def _save(self):
        """Persist the in-memory cache to disk (caller must hold lock)."""
        self.store.write_json(REGISTRY_PATH, self._data)

    def _generate_strategy_id(self) -> str:
        """Thread-safe strategy ID generator: STRAT_001, STRAT_002, ..."""
        # Caller must hold _lock
        self._id_counter += 1
        return f"STRAT_{self._id_counter:03d}"

    def _now(self) -> str:
        """Return current UTC time as ISO-8601 string."""
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _today(self) -> str:
        """Return current UTC date as YYYY-MM-DD."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, name: str, category: str, platform: str,
                 parameters: dict, notes: str = "") -> dict:
        """Register a new strategy.

        Args:
            name: Strategy name (e.g. "POLY_ARB_SCANNER"). Must be unique.
            category: Strategy category (e.g. "arbitrage").
            platform: Target platform (e.g. "polymarket").
            parameters: Initial parameter dict.
            notes: Optional notes string.

        Returns:
            The new registry entry dict.

        Raises:
            ValueError: If a strategy with this name is already registered.
        """
        with self._lock:
            if name in self._data:
                raise ValueError(f"Strategy '{name}' is already registered")

            strategy_id = self._generate_strategy_id()
            now = self._now()
            today = self._today()

            lifecycle = copy.copy(_EMPTY_LIFECYCLE)
            lifecycle["scouted"] = now

            entry = {
                "strategy_id": strategy_id,
                "status": "scouted",
                "version": "1.0",
                "category": category,
                "platform": platform,
                "parameters": copy.deepcopy(parameters),
                "parameter_history": [
                    {"version": "1.0", "date": today, "params": copy.deepcopy(parameters)}
                ],
                "lifecycle": lifecycle,
                "backtest_ids": [],
                "account_ids": [],
                "notes": notes,
            }

            self._data[name] = entry
            self._save()

        self.audit.log_event(
            topic="registry:strategy_registered",
            producer="POLY_STRATEGY_REGISTRY",
            payload={"name": name, "strategy_id": strategy_id, "category": category, "platform": platform},
        )

        return copy.deepcopy(entry)

    def get(self, name: str) -> dict | None:
        """Return a copy of the registry entry for a strategy, or None if not found."""
        with self._lock:
            entry = self._data.get(name)
            return copy.deepcopy(entry) if entry is not None else None

    def get_all(self) -> dict:
        """Return a deep copy of all registry entries."""
        with self._lock:
            return copy.deepcopy(self._data)

    def update_status(self, name: str, new_status: str) -> dict:
        """Update the status of a registered strategy.

        Sets the corresponding lifecycle timestamp if not already set.

        Args:
            name: Strategy name.
            new_status: One of VALID_STATUSES.

        Returns:
            Updated entry dict.

        Raises:
            ValueError: If the name is unknown or status is invalid.
        """
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{new_status}'. Must be one of {VALID_STATUSES}")

        with self._lock:
            if name not in self._data:
                raise ValueError(f"Strategy '{name}' not found in registry")

            entry = self._data[name]
            old_status = entry["status"]
            entry["status"] = new_status

            # Set lifecycle timestamp once (do not overwrite if already set)
            lifecycle_field = STATUS_TO_LIFECYCLE.get(new_status)
            if lifecycle_field and entry["lifecycle"].get(lifecycle_field) is None:
                entry["lifecycle"][lifecycle_field] = self._now()

            self._save()
            entry_copy = copy.deepcopy(entry)

        self.audit.log_event(
            topic="registry:status_updated",
            producer="POLY_STRATEGY_REGISTRY",
            payload={"name": name, "old_status": old_status, "new_status": new_status},
        )

        return entry_copy

    def update_parameters(self, name: str, new_params: dict,
                          new_version: str | None = None) -> dict:
        """Update the active parameters of a strategy.

        Appends to parameter_history and bumps the version.

        Args:
            name: Strategy name.
            new_params: New parameter dict (replaces current parameters).
            new_version: Optional version string. If None, auto-increments minor version.

        Returns:
            Updated entry dict.

        Raises:
            ValueError: If the name is unknown.
        """
        with self._lock:
            if name not in self._data:
                raise ValueError(f"Strategy '{name}' not found in registry")

            entry = self._data[name]

            if new_version is None:
                # Auto-increment minor version: "1.0" → "1.1", "1.9" → "1.10"
                parts = entry["version"].split(".")
                try:
                    major = int(parts[0])
                    minor = int(parts[1]) if len(parts) > 1 else 0
                    new_version = f"{major}.{minor + 1}"
                except (ValueError, IndexError):
                    new_version = entry["version"] + ".1"

            entry["parameters"] = copy.deepcopy(new_params)
            entry["version"] = new_version
            entry["parameter_history"].append({
                "version": new_version,
                "date": self._today(),
                "params": copy.deepcopy(new_params),
            })

            self._save()
            entry_copy = copy.deepcopy(entry)

        self.audit.log_event(
            topic="registry:parameters_updated",
            producer="POLY_STRATEGY_REGISTRY",
            payload={"name": name, "new_version": new_version},
        )

        return entry_copy

    def add_backtest_id(self, name: str, backtest_id: str) -> dict:
        """Append a backtest ID to a strategy's record.

        Raises:
            ValueError: If the name is unknown.
        """
        with self._lock:
            if name not in self._data:
                raise ValueError(f"Strategy '{name}' not found in registry")
            self._data[name]["backtest_ids"].append(backtest_id)
            self._save()
            return copy.deepcopy(self._data[name])

    def add_account_id(self, name: str, account_id: str) -> dict:
        """Append an account ID to a strategy's record.

        Raises:
            ValueError: If the name is unknown.
        """
        with self._lock:
            if name not in self._data:
                raise ValueError(f"Strategy '{name}' not found in registry")
            self._data[name]["account_ids"].append(account_id)
            self._save()
            return copy.deepcopy(self._data[name])
