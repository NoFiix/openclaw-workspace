"""
POLY_RISK_GUARDIAN — Portfolio-level pre-trade risk guard.

Scope: the global portfolio (all active strategies combined).
Enforces three hard limits on every proposed trade:

  1. Max 5 simultaneous open positions (all strategies combined)
  2. Max 80% of total capital exposed at any time
  3. Max 40% of total capital in any single strategy category (anti-correlation)

Called synchronously pre-trade by the orchestrator. Returns Go/No-Go immediately.
Also publishes risk:portfolio_check to the bus for audit purposes.

Demarcation:
- POLY_KILL_SWITCH  → per-strategy drawdown / consecutive losses
- POLY_RISK_GUARDIAN → portfolio exposure / position count / category concentration
- POLY_GLOBAL_RISK_GUARD → cumulative system-wide losses
"""

import copy
import threading
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus


CONSUMER_ID = "POLY_RISK_GUARDIAN"

# Portfolio-level hard limits
MAX_POSITIONS = 5          # max simultaneous open positions (all strategies)
MAX_EXPOSURE_PCT = 0.80    # max fraction of total capital exposed
MAX_CATEGORY_PCT = 0.40    # max fraction per strategy category (anti-correlation)

STATE_FILE = "risk/portfolio_state.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PolyRiskGuardian:
    """Portfolio-level pre-trade guard: position count, exposure, category concentration."""

    def __init__(self, base_path="state"):
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self._lock = threading.Lock()
        self._state = self._load_state()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> dict:
        data = self.store.read_json(STATE_FILE)
        if data is None:
            data = {"open_positions": [], "last_updated": None}
        return data

    def _save_state(self) -> None:
        """Caller must hold _lock."""
        self._state["last_updated"] = _now_utc()
        self.store.write_json(STATE_FILE, self._state)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        proposed_size_eur: float,
        proposed_category: str,
        total_capital_eur: float,
    ) -> dict:
        """Synchronous pre-trade portfolio check.

        Evaluates whether adding the proposed trade would breach any portfolio
        limit. Checks are applied in priority order; the first failing check
        populates `blocked_by`.

        Args:
            proposed_size_eur: Capital the proposed trade would commit (EUR).
            proposed_category: Strategy category (e.g. "bundle_arb", "weather_arb").
            total_capital_eur: Sum of current capital across all active strategy accounts.

        Returns:
            Dict with:
                allowed (bool)            — overall decision
                blocked_by (str|None)     — first failing check name, or None
                checks (dict)             — {exposure_ok, positions_ok, category_ok}
                current_positions (int)   — positions open before this trade
                current_exposure_eur (float)
                current_exposure_pct (float)
                proposed_size_eur (float)
                total_capital_eur (float)
        """
        with self._lock:
            positions = self._state.get("open_positions", [])
            n_positions = len(positions)
            current_exposure = sum(p["size_eur"] for p in positions)

        # --- Check 1: position count ---
        positions_ok = n_positions < MAX_POSITIONS

        # --- Check 2: total exposure ---
        new_exposure = current_exposure + proposed_size_eur
        if total_capital_eur > 0:
            exposure_pct = new_exposure / total_capital_eur
        else:
            exposure_pct = 1.0
        exposure_ok = exposure_pct <= MAX_EXPOSURE_PCT

        # --- Check 3: category concentration ---
        with self._lock:
            positions = self._state.get("open_positions", [])
        category_exposure = (
            sum(p["size_eur"] for p in positions if p.get("category") == proposed_category)
            + proposed_size_eur
        )
        if total_capital_eur > 0:
            category_pct = category_exposure / total_capital_eur
        else:
            category_pct = 1.0
        category_ok = category_pct <= MAX_CATEGORY_PCT

        checks = {
            "exposure_ok": exposure_ok,
            "positions_ok": positions_ok,
            "category_ok": category_ok,
        }
        allowed = all(checks.values())

        # First failing check determines blocked_by (priority order)
        blocked_by = None
        if not positions_ok:
            blocked_by = "max_positions"
        elif not exposure_ok:
            blocked_by = "max_exposure"
        elif not category_ok:
            blocked_by = "max_category_concentration"

        current_exposure_pct = (
            round(current_exposure / total_capital_eur, 6) if total_capital_eur > 0 else 0.0
        )

        result = {
            "allowed": allowed,
            "blocked_by": blocked_by,
            "checks": checks,
            "current_positions": n_positions,
            "current_exposure_eur": round(current_exposure, 6),
            "current_exposure_pct": current_exposure_pct,
            "proposed_size_eur": proposed_size_eur,
            "total_capital_eur": total_capital_eur,
        }

        self.bus.publish("risk:portfolio_check", CONSUMER_ID, result)
        self.audit.log_event("risk:portfolio_check", CONSUMER_ID, result)

        return result

    def add_position(
        self,
        strategy: str,
        market_id: str,
        size_eur: float,
        category: str,
    ) -> None:
        """Register a new open position after a trade is executed.

        Args:
            strategy: Strategy that opened the position.
            market_id: Market identifier.
            size_eur: Capital committed (EUR).
            category: Strategy category (e.g. "bundle_arb").
        """
        with self._lock:
            self._state.setdefault("open_positions", []).append({
                "strategy": strategy,
                "market_id": market_id,
                "size_eur": size_eur,
                "category": category,
                "opened_at": _now_utc(),
            })
            self._save_state()

    def close_position(self, strategy: str, market_id: str) -> None:
        """Remove an open position when its market resolves.

        If the position is not found (e.g. already closed), this is a no-op.

        Args:
            strategy: Strategy that owned the position.
            market_id: Market identifier.
        """
        with self._lock:
            positions = self._state.get("open_positions", [])
            for i, p in enumerate(positions):
                if p["strategy"] == strategy and p["market_id"] == market_id:
                    positions.pop(i)
                    break
            self._save_state()

    def get_state(self) -> dict:
        """Return a deep copy of the current portfolio state."""
        with self._lock:
            return copy.deepcopy(self._state)
