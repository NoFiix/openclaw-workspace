"""
POLY_CAPITAL_MANAGER — Strategy account lifecycle and capital gating.

Responsibilities:
  1. Create live POLY_STRATEGY_ACCOUNT on promotion:approved bus event.
     Gate DECIDES, Capital Manager EXECUTES — never create live accounts
     without a promotion:approved event.
  2. Pre-trade capital check (filter 6 in the 7-filter chain): verify the
     strategy account has enough available capital for the proposed trade.
  3. Capital recovery: when POLY_KILL_SWITCH emits stop_strategy, archive
     the account and release its capital slot.

Bus topics consumed:
  - promotion:approved  → create_live_account()
  - risk:kill_switch    → recover_capital() if action == "stop_strategy"

Bus topics published:
  - account:live_created  — after successful live account creation
  - account:live_closed   — after capital recovery (strategy stopped)

Frequency: pre-trade (check_capital) + tick 60s (run_once) + on event.
"""

from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_strategy_account import PolyStrategyAccount


CONSUMER_ID = "POLY_CAPITAL_MANAGER"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PolyCapitalManager:
    """Strategy account lifecycle manager and pre-trade capital gate."""

    def __init__(self, base_path="state"):
        self.base_path = base_path
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_live_account(self, payload: dict) -> dict:
        """Create a live PolyStrategyAccount from a promotion:approved payload.

        If a paper account already exists for this strategy it is archived
        first (update_status("stopped") → archive()).  Then a fresh account
        is created with the capital specified in the payload and its status
        is set to "active".

        Args:
            payload: promotion:approved payload with keys:
                strategy         — strategy name (e.g. "POLY_ARB_SCANNER")
                initial_capital_eur — starting capital in EUR (default 1 000)

        Returns:
            Dict with: account_id, strategy, initial_capital_eur, status.
        """
        strategy = payload["strategy"]
        initial_capital = float(payload.get("initial_capital_eur", 1000.0))
        account_id = f"ACC_{strategy}"

        # Archive any existing account (paper testing) to free the slot
        try:
            existing = PolyStrategyAccount.load(account_id, self.base_path)
            existing.update_status("stopped")  # triggers archive()
        except FileNotFoundError:
            pass

        # Create fresh live account
        account = PolyStrategyAccount.create(
            strategy, "polymarket",
            base_path=self.base_path,
            initial_capital=initial_capital,
        )
        account.update_status("active")

        result = {
            "account_id": account_id,
            "strategy": strategy,
            "initial_capital_eur": initial_capital,
            "status": "active",
        }

        self.bus.publish("account:live_created", CONSUMER_ID, result)
        self.audit.log_event("account:live_created", CONSUMER_ID, result)

        return result

    def check_capital(self, account_id: str, size_eur: float) -> dict:
        """Pre-trade capital check (filter 6 in the 7-filter chain).

        Verifies that the strategy account has enough available capital to
        cover the proposed trade size.  This is a synchronous, read-only
        check — no state is mutated.

        Args:
            account_id: Full account ID (e.g. "ACC_POLY_ARB_SCANNER").
            size_eur:   Proposed trade size in EUR.

        Returns:
            Dict with: allowed (bool), available_capital_eur (float),
            required_eur (float), reason (str|None).
        """
        try:
            account = PolyStrategyAccount.load(account_id, self.base_path)
        except FileNotFoundError:
            return {
                "allowed": False,
                "available_capital_eur": 0.0,
                "required_eur": size_eur,
                "reason": "account_not_found",
            }

        available = account.data["capital"]["available"]
        allowed = size_eur <= available

        return {
            "allowed": allowed,
            "available_capital_eur": available,
            "required_eur": size_eur,
            "reason": "insufficient_capital" if not allowed else None,
        }

    def recover_capital(self, strategy: str, account_id: str) -> dict:
        """Archive a stopped strategy's account and release its capital slot.

        Called when POLY_KILL_SWITCH emits action="stop_strategy".
        Sets account status to "stopped" which triggers archive().
        Publishes account:live_closed to the bus and audit log.

        If the account is not found (e.g. already archived), this is a
        no-op that returns recovered_capital_eur=0.0.

        Args:
            strategy:   Strategy name.
            account_id: Full account ID.

        Returns:
            Dict with: strategy, account_id, recovered_capital_eur, status.
        """
        try:
            account = PolyStrategyAccount.load(account_id, self.base_path)
        except FileNotFoundError:
            return {
                "strategy": strategy,
                "account_id": account_id,
                "recovered_capital_eur": 0.0,
                "status": "not_found",
            }

        recovered_capital = round(account.data["capital"]["current"], 6)
        account.update_status("stopped")  # triggers archive()

        result = {
            "strategy": strategy,
            "account_id": account_id,
            "recovered_capital_eur": recovered_capital,
            "status": "stopped",
        }

        self.bus.publish("account:live_closed", CONSUMER_ID, result)
        self.audit.log_event("account:live_closed", CONSUMER_ID, result)

        return result

    def run_once(self) -> dict:
        """Poll bus events and process account lifecycle changes.

        Handles:
          - promotion:approved → create_live_account()
          - risk:kill_switch (action=stop_strategy) → recover_capital()

        All events are acked after processing regardless of outcome.

        Returns:
            Dict with: created (list of create_live_account results),
            recovered (list of recover_capital results).
        """
        created = []
        recovered = []

        # --- promotion:approved ---
        promotion_events = self.bus.poll(
            CONSUMER_ID, topics=["promotion:approved"]
        )
        for evt in promotion_events:
            payload = evt.get("payload", {})
            result = self.create_live_account(payload)
            created.append(result)
            self.bus.ack(CONSUMER_ID, evt["event_id"])

        # --- risk:kill_switch (stop_strategy only) ---
        kill_events = self.bus.poll(
            CONSUMER_ID, topics=["risk:kill_switch"]
        )
        for evt in kill_events:
            payload = evt.get("payload", {})
            if payload.get("action") == "stop_strategy":
                result = self.recover_capital(
                    payload["strategy"], payload["account_id"]
                )
                recovered.append(result)
            self.bus.ack(CONSUMER_ID, evt["event_id"])

        return {"created": created, "recovered": recovered}
