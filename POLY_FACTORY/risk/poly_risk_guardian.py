"""
POLY_RISK_GUARDIAN — Portfolio-level pre-trade risk guard.

Enforces per-strategy and portfolio-level limits on every proposed trade:

  1. Max 6 simultaneous open positions PER STRATEGY (isolated capital model)
  2. Max 40% of a strategy's own capital committed at any time
  3. Max 80% of total capital exposed at any time (all strategies combined)
  4. Max 40% of total capital in any single strategy category (anti-correlation)

Called synchronously pre-trade by the orchestrator. Returns Go/No-Go immediately.
Also publishes risk:portfolio_check to the bus for audit purposes.

Demarcation:
- POLY_KILL_SWITCH  → per-strategy drawdown / consecutive losses
- POLY_RISK_GUARDIAN → portfolio exposure / position count / category concentration
- POLY_GLOBAL_RISK_GUARD → cumulative system-wide losses
"""

import copy
import logging
import threading
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus

logger = logging.getLogger("POLY_RISK_GUARDIAN")

CONSUMER_ID = "POLY_RISK_GUARDIAN"

# Per-strategy limits (isolated capital model)
MAX_POSITIONS_PER_STRATEGY = 6     # max simultaneous open positions per strategy
MAX_CAPITAL_USAGE_PER_STRATEGY = 0.40  # max fraction of strategy's own capital committed

# Portfolio-level hard limits
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
        """Load portfolio state from disk.

        Guards against missing, empty, or corrupt files:
        - missing file → fresh state
        - empty or corrupt JSON → fresh state + log warning
        - missing open_positions key → fresh state + log warning
        """
        try:
            data = self.store.read_json(STATE_FILE)
        except Exception:
            logger.warning(
                "portfolio_state.json corrupt or unreadable — resetting to empty state"
            )
            return {"open_positions": [], "last_updated": None}
        if data is None:
            logger.info("portfolio_state.json not found — starting with empty state")
            return {"open_positions": [], "last_updated": None}
        if not isinstance(data, dict) or "open_positions" not in data:
            logger.warning(
                "portfolio_state.json invalid or missing open_positions — resetting to empty state"
            )
            return {"open_positions": [], "last_updated": None}
        logger.info(
            "portfolio_state.json loaded: %d open positions",
            len(data["open_positions"]),
        )
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
        strategy: str = "",
        strategy_capital: float = 0.0,
    ) -> dict:
        """Synchronous pre-trade portfolio check.

        Evaluates whether adding the proposed trade would breach any limit.
        Checks are applied in priority order; the first failing check
        populates `blocked_by`.

        Args:
            proposed_size_eur: Capital the proposed trade would commit (EUR).
            proposed_category: Strategy category (e.g. "bundle_arb", "weather_arb").
            total_capital_eur: Sum of current capital across all active strategy accounts.
            strategy: Strategy name (for per-strategy position/capital limits).
            strategy_capital: Current capital of the strategy's account (EUR).

        Returns:
            Dict with:
                allowed (bool)            — overall decision
                blocked_by (str|None)     — first failing check name, or None
                checks (dict)             — {positions_ok, strategy_capital_ok, exposure_ok, category_ok}
                current_positions (int)   — total positions open before this trade
                strategy_positions (int)  — positions open for this strategy
                current_exposure_eur (float)
                current_exposure_pct (float)
                proposed_size_eur (float)
                total_capital_eur (float)
        """
        with self._lock:
            positions = list(self._state.get("open_positions", []))

        n_positions = len(positions)
        current_exposure = sum(p["size_eur"] for p in positions)

        # --- Check 1: per-strategy position count ---
        strat_positions = [p for p in positions if p.get("strategy") == strategy]
        n_strat_positions = len(strat_positions)
        positions_ok = n_strat_positions < MAX_POSITIONS_PER_STRATEGY

        # --- Check 2: per-strategy capital usage ---
        strat_committed = sum(p["size_eur"] for p in strat_positions)
        if strategy_capital > 0:
            strat_usage_pct = (strat_committed + proposed_size_eur) / strategy_capital
        else:
            strat_usage_pct = 1.0
        strategy_capital_ok = strat_usage_pct <= MAX_CAPITAL_USAGE_PER_STRATEGY

        # --- Check 3: total exposure ---
        new_exposure = current_exposure + proposed_size_eur
        if total_capital_eur > 0:
            exposure_pct = new_exposure / total_capital_eur
        else:
            exposure_pct = 1.0
        exposure_ok = exposure_pct <= MAX_EXPOSURE_PCT

        # --- Check 4: category concentration ---
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
            "positions_ok": positions_ok,
            "strategy_capital_ok": strategy_capital_ok,
            "exposure_ok": exposure_ok,
            "category_ok": category_ok,
        }
        allowed = all(checks.values())

        # First failing check determines blocked_by (priority order)
        blocked_by = None
        if not positions_ok:
            blocked_by = "strategy_position_limit"
        elif not strategy_capital_ok:
            blocked_by = "strategy_capital_limit"
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
            "strategy_positions": n_strat_positions,
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

        If a position with the same (strategy, market_id) already exists,
        the size_eur is merged (accumulated) instead of creating a duplicate.

        Args:
            strategy: Strategy that opened the position.
            market_id: Market identifier.
            size_eur: Capital committed (EUR).
            category: Strategy category (e.g. "bundle_arb").
        """
        with self._lock:
            positions = self._state.setdefault("open_positions", [])
            for p in positions:
                if p["strategy"] == strategy and p["market_id"] == market_id:
                    old_size = p["size_eur"]
                    p["size_eur"] += size_eur
                    logger.info(
                        "position merged: %s on %s — %.2f€ + %.2f€ = %.2f€",
                        strategy, market_id[:16], old_size, size_eur, p["size_eur"],
                    )
                    self._save_state()
                    return
            positions.append({
                "strategy": strategy,
                "market_id": market_id,
                "size_eur": size_eur,
                "category": category,
                "opened_at": _now_utc(),
            })
            logger.info(
                "position added: %s on %s — %.2f€ (total open: %d)",
                strategy, market_id[:16], size_eur, len(positions),
            )
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

    def close_positions_for_market(self, market_id: str) -> int:
        """Close all positions on a resolved market (all strategies).

        Args:
            market_id: Market identifier that resolved.

        Returns:
            Number of positions closed.
        """
        with self._lock:
            positions = self._state.get("open_positions", [])
            before = len(positions)
            self._state["open_positions"] = [
                p for p in positions if p["market_id"] != market_id
            ]
            closed = before - len(self._state["open_positions"])
            if closed > 0:
                self._save_state()
            return closed

    def get_state(self) -> dict:
        """Return a deep copy of the current portfolio state."""
        with self._lock:
            return copy.deepcopy(self._state)
