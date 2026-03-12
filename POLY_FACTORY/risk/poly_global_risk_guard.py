"""
POLY_GLOBAL_RISK_GUARD — System-wide cumulative loss ceiling.

Scope: the entire POLY_FACTORY system (all strategies combined).
Enforces one hard rule: if cumulative losses across ALL strategy accounts
reach 4 000€, everything stops (ARRET_TOTAL).

4 status levels (ascending severity):
    NORMAL      — total loss < 2 000€  — no action
    ALERTE      — 2 000–2 999€         — block new live promotions
    CRITIQUE    — 3 000–3 999€         — block new live promotions
    ARRET_TOTAL — ≥ 4 000€             — halt all trading

Publishes risk:global_status on the bus when status changes.
Called every 60s by the orchestrator (run_once) and post-trade.

Demarcation:
- POLY_KILL_SWITCH      → per-strategy drawdown / consecutive losses
- POLY_RISK_GUARDIAN    → portfolio exposure / position count / category
- POLY_GLOBAL_RISK_GUARD → cumulative system-wide losses ceiling
"""

import copy
import threading
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_strategy_account import PolyStrategyAccount


CONSUMER_ID = "POLY_GLOBAL_RISK_GUARD"

# Cumulative loss thresholds (EUR, positive values)
MAX_LOSS_EUR          = 4000.0   # ARRET_TOTAL if total loss reaches this
CRITIQUE_THRESHOLD_EUR = 3000.0  # CRITIQUE starts here
ALERTE_THRESHOLD_EUR  = 2000.0   # ALERTE starts here

# Status strings
STATUS_NORMAL      = "NORMAL"
STATUS_ALERTE      = "ALERTE"
STATUS_CRITIQUE    = "CRITIQUE"
STATUS_ARRET_TOTAL = "ARRET_TOTAL"

STATE_FILE = "risk/global_risk_state.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PolyGlobalRiskGuard:
    """System-wide cumulative loss ceiling guard."""

    def __init__(self, base_path="state"):
        self.base_path = base_path
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
            data = {
                "status": STATUS_NORMAL,
                "total_loss_eur": 0.0,
                "pct_used": 0.0,
                "registered_accounts": [],
                "accounts_contributing": {},
                "last_checked": None,
                "last_updated": None,
            }
        return data

    def _save_state(self) -> None:
        """Caller must hold _lock."""
        self._state["last_updated"] = _now_utc()
        self.store.write_json(STATE_FILE, self._state)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _status_from_loss(self, total_loss_eur: float) -> str:
        if total_loss_eur >= MAX_LOSS_EUR:
            return STATUS_ARRET_TOTAL
        if total_loss_eur >= CRITIQUE_THRESHOLD_EUR:
            return STATUS_CRITIQUE
        if total_loss_eur >= ALERTE_THRESHOLD_EUR:
            return STATUS_ALERTE
        return STATUS_NORMAL

    def _action_from_status(self, status: str) -> str:
        if status == STATUS_ARRET_TOTAL:
            return "halt_all_trading"
        if status in (STATUS_ALERTE, STATUS_CRITIQUE):
            return "block_new_live_promotions"
        return "none"

    def _compute_total_loss(self) -> tuple:
        """Read all registered accounts and sum only the losses.

        Returns:
            (total_loss_eur, accounts_contributing) where total_loss_eur is
            a positive float and accounts_contributing maps account_id to
            its negative pnl.total (only losing accounts appear).
        """
        with self._lock:
            accounts = list(self._state.get("registered_accounts", []))

        total_loss = 0.0
        contributing = {}
        for account_id in accounts:
            try:
                account = PolyStrategyAccount.load(account_id, self.base_path)
                pnl_total = account.data["pnl"]["total"]
                if pnl_total < 0:
                    total_loss += abs(pnl_total)
                    contributing[account_id] = round(pnl_total, 2)
            except FileNotFoundError:
                pass  # Account not yet created or archived — skip

        return round(total_loss, 2), contributing

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, account_id: str) -> None:
        """Register an account for system-wide loss monitoring.

        Idempotent — registering an already-registered account is a no-op.

        Args:
            account_id: Full account ID (e.g. "ACC_POLY_ARB_SCANNER").
        """
        with self._lock:
            accounts = self._state.setdefault("registered_accounts", [])
            if account_id not in accounts:
                accounts.append(account_id)
                self._save_state()

    def evaluate(self) -> dict:
        """Compute current global risk status from all registered accounts.

        Reads every registered account, sums losses (only pnl.total < 0),
        determines the status level, and updates the state file.

        Publishes risk:global_status on the bus and to the audit log only
        when the status changes (dedup guard prevents event flooding on
        every 60s tick when the situation is stable).

        Returns:
            Dict with: status, total_loss_eur, max_loss_eur, pct_used,
            action_taken, accounts_contributing.
        """
        total_loss_eur, accounts_contributing = self._compute_total_loss()
        status = self._status_from_loss(total_loss_eur)
        pct_used = round(total_loss_eur / MAX_LOSS_EUR, 6)
        action_taken = self._action_from_status(status)
        now = _now_utc()

        result = {
            "status": status,
            "total_loss_eur": total_loss_eur,
            "max_loss_eur": MAX_LOSS_EUR,
            "pct_used": pct_used,
            "action_taken": action_taken,
            "accounts_contributing": accounts_contributing,
        }

        with self._lock:
            previous_status = self._state.get("status", STATUS_NORMAL)
            self._state.update({
                "status": status,
                "total_loss_eur": total_loss_eur,
                "pct_used": pct_used,
                "accounts_contributing": accounts_contributing,
                "last_checked": now,
            })
            self._save_state()

        # Publish only when status changes
        if status != previous_status:
            self.bus.publish("risk:global_status", CONSUMER_ID, result)
            self.audit.log_event("risk:global_status", CONSUMER_ID, result)

        return result

    def check_pre_trade(self) -> dict:
        """Fast cached pre-trade check (no disk I/O).

        Trading is allowed at NORMAL, ALERTE, and CRITIQUE.
        Trading is halted only at ARRET_TOTAL (≥ 4 000€ cumulative loss).

        Returns:
            Dict with: allowed (bool), status (str), reason (str|None).
        """
        with self._lock:
            status = self._state.get("status", STATUS_NORMAL)
        allowed = status != STATUS_ARRET_TOTAL
        return {
            "allowed": allowed,
            "status": status,
            "reason": "global_loss_limit_reached" if not allowed else None,
        }

    def get_state(self) -> dict:
        """Return a deep copy of the current global risk state."""
        with self._lock:
            return copy.deepcopy(self._state)

    def run_once(self) -> dict:
        """Tick evaluation — called every 60s by the orchestrator.

        Returns:
            Result dict from evaluate().
        """
        return self.evaluate()
