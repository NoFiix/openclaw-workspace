"""
POLY_KILL_SWITCH — Per-strategy kill switch with 5 response levels.

Safety-critical. Protects each strategy against daily drawdown, total drawdown,
consecutive losses, and feed staleness. Emits high-priority risk:kill_switch events.
Never bypassed — all pre-trade checks run through check_pre_trade().

5 response levels (ascending severity):
    OK            — all clear, trading allowed
    WARNING       — approaching daily limit, trading allowed
    PAUSE_DAILY   — paused until midnight (daily drawdown or consecutive losses)
    PAUSE_SESSION — paused until condition clears (feed staleness)
    STOP_STRATEGY — permanently stopped (total drawdown exceeded)
"""

import threading
from datetime import datetime, timedelta, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_strategy_account import PolyStrategyAccount


CONSUMER_ID = "POLY_KILL_SWITCH"

# Thresholds — match POLY_STRATEGY_ACCOUNT defaults
DAILY_DRAWDOWN_LIMIT_PCT = -100.0   # paper mode: let strategies run to full loss for observation
TOTAL_DRAWDOWN_LIMIT_PCT = -100.0   # paper mode: let strategies run to full loss for observation
# NOTE: restore -5.0 / -30.0 before any live deployment
MAX_CONSECUTIVE_LOSSES = 3         # pause after 3 consecutive losing trades
FEED_STALE_THRESHOLD_SECONDS = 300 # pause if price feed older than 5 minutes
WARNING_RATIO = 0.8                # warn at 80% of daily limit (-4%)

# 5 response levels
LEVEL_OK = "OK"
LEVEL_WARNING = "WARNING"
LEVEL_PAUSE_DAILY = "PAUSE_DAILY"
LEVEL_PAUSE_SESSION = "PAUSE_SESSION"
LEVEL_STOP_STRATEGY = "STOP_STRATEGY"

# Levels that block pre-trade execution
BLOCKED_LEVELS = {LEVEL_PAUSE_DAILY, LEVEL_PAUSE_SESSION, LEVEL_STOP_STRATEGY}

STATE_FILE = "risk/kill_switch_status.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_midnight_utc() -> str:
    """Return ISO timestamp of next UTC midnight."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return tomorrow.strftime("%Y-%m-%dT%H:%M:%SZ")


class PolyKillSwitch:
    """Per-strategy kill switch: drawdown, consecutive losses, feed health."""

    def __init__(self, base_path="state"):
        self.base_path = base_path
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self._lock = threading.Lock()
        self._status = {}
        self._load_status()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_status(self) -> None:
        data = self.store.read_json(STATE_FILE) or {}
        self._status = data

    def _save_status(self) -> None:
        """Caller must hold _lock."""
        self.store.write_json(STATE_FILE, self._status)

    def _default_entry(self, account_id: str) -> dict:
        return {
            "account_id": account_id,
            "level": LEVEL_OK,
            "action": None,
            "consecutive_losses": 0,
            "triggered_at": None,
            "resume_at": None,
            "reason": None,
            "drawdown_pct": None,
            "threshold_pct": None,
            "last_checked": None,
        }

    # ------------------------------------------------------------------
    # Internal trigger helpers
    # ------------------------------------------------------------------

    def _trigger(
        self,
        strategy: str,
        account_id: str,
        level: str,
        action: str,
        reason: str,
        drawdown_pct=None,
        threshold_pct=None,
    ) -> dict:
        """Trigger a kill switch event.

        Updates internal state, publishes a high-priority risk:kill_switch bus
        event, and writes to the audit log. Dedup guard: if the strategy is
        already at the same level for the same reason, the bus event is NOT
        re-published (prevents flooding on every tick).

        Returns:
            Result dict with level, action, reason, resume_at.
        """
        with self._lock:
            entry = self._status.setdefault(strategy, self._default_entry(account_id))

            # Dedup: already at same level+reason, skip re-publishing
            if entry.get("level") == level and entry.get("reason") == reason:
                entry["last_checked"] = _now_utc()
                self._save_status()
                return {
                    "strategy": strategy,
                    "account_id": account_id,
                    "level": level,
                    "action": action,
                    "reason": reason,
                    "drawdown_pct": entry.get("drawdown_pct"),
                    "threshold_pct": entry.get("threshold_pct"),
                    "triggered_at": entry.get("triggered_at"),
                    "resume_at": entry.get("resume_at"),
                }

            now = _now_utc()
            resume_at = _next_midnight_utc() if level == LEVEL_PAUSE_DAILY else None

            entry.update({
                "account_id": account_id,
                "level": level,
                "action": action,
                "reason": reason,
                "drawdown_pct": drawdown_pct,
                "threshold_pct": threshold_pct,
                "triggered_at": now,
                "resume_at": resume_at,
                "last_checked": now,
            })
            self._save_status()

        payload = {
            "action": action,
            "strategy": strategy,
            "account_id": account_id,
            "reason": reason,
            "drawdown_pct": drawdown_pct,
            "threshold_pct": threshold_pct,
            "resume_at": resume_at,
        }

        self.bus.publish("risk:kill_switch", CONSUMER_ID, payload, priority="high")
        self.audit.log_event("risk:kill_switch", CONSUMER_ID, payload, priority="high")

        return {
            "strategy": strategy,
            "account_id": account_id,
            "level": level,
            "action": action,
            "reason": reason,
            "drawdown_pct": drawdown_pct,
            "threshold_pct": threshold_pct,
            "triggered_at": now,
            "resume_at": resume_at,
        }

    def _update_level(self, strategy: str, account_id: str, level: str) -> dict:
        """Update status for non-blocking levels (OK / WARNING).

        Never downgrades a STOP_STRATEGY — once stopped, always stopped
        until explicit intervention.
        """
        with self._lock:
            entry = self._status.setdefault(strategy, self._default_entry(account_id))

            # Hard stop is permanent — ignore downgrade attempts
            if entry.get("level") == LEVEL_STOP_STRATEGY:
                return {
                    "strategy": strategy,
                    "account_id": account_id,
                    "level": LEVEL_STOP_STRATEGY,
                    "action": entry.get("action"),
                    "reason": entry.get("reason"),
                }

            entry.update({
                "account_id": account_id,
                "level": level,
                "last_checked": _now_utc(),
            })
            # Clear trigger data for non-blocked levels
            if level in (LEVEL_OK, LEVEL_WARNING):
                entry["action"] = None
                entry["triggered_at"] = None
                entry["resume_at"] = None
                entry["drawdown_pct"] = None
                entry["threshold_pct"] = None
                if level == LEVEL_OK:
                    entry["reason"] = None
            self._save_status()

        return {
            "strategy": strategy,
            "account_id": account_id,
            "level": level,
            "action": None,
            "reason": entry.get("reason") if level == LEVEL_WARNING else None,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, strategy: str, account_id: str) -> None:
        """Register a strategy so run_once() will evaluate it on each tick."""
        with self._lock:
            if strategy not in self._status:
                self._status[strategy] = self._default_entry(account_id)
                self._save_status()

    def evaluate(self, strategy: str, account_id: str) -> dict:
        """Full kill switch evaluation for one strategy.

        Checks conditions in priority order and returns the first match.
        Safe to call on every tick — dedup guard prevents bus flooding.

        Args:
            strategy: Strategy name (e.g. "POLY_ARB_SCANNER").
            account_id: Full account ID (e.g. "ACC_POLY_ARB_SCANNER").

        Returns:
            Result dict: {strategy, account_id, level, action, reason, ...}

        Raises:
            FileNotFoundError: If the account file does not exist.
        """
        account = PolyStrategyAccount.load(account_id, self.base_path)
        data = account.data

        current_dd = data["drawdown"]["current_drawdown_pct"]
        daily_pnl_pct = data["drawdown"]["daily_pnl_pct"]

        # 1. Total drawdown → permanent stop
        if current_dd < TOTAL_DRAWDOWN_LIMIT_PCT:
            return self._trigger(
                strategy, account_id,
                LEVEL_STOP_STRATEGY, "stop_strategy", "total_drawdown_exceeded",
                current_dd, TOTAL_DRAWDOWN_LIMIT_PCT,
            )

        # 2. Daily drawdown → pause until midnight
        if daily_pnl_pct < DAILY_DRAWDOWN_LIMIT_PCT:
            return self._trigger(
                strategy, account_id,
                LEVEL_PAUSE_DAILY, "pause_strategy", "daily_drawdown_exceeded",
                daily_pnl_pct, DAILY_DRAWDOWN_LIMIT_PCT,
            )

        # 3. Consecutive losses → pause until midnight
        with self._lock:
            consec = self._status.get(strategy, {}).get("consecutive_losses", 0)
        if consec >= MAX_CONSECUTIVE_LOSSES:
            return self._trigger(
                strategy, account_id,
                LEVEL_PAUSE_DAILY, "pause_strategy", "consecutive_losses_exceeded",
                None, float(MAX_CONSECUTIVE_LOSSES),
            )

        # 4. Approaching daily limit → warning
        if daily_pnl_pct < DAILY_DRAWDOWN_LIMIT_PCT * WARNING_RATIO:
            return self._update_level(strategy, account_id, LEVEL_WARNING)

        # 5. All clear
        return self._update_level(strategy, account_id, LEVEL_OK)

    def record_trade_result(self, strategy: str, pnl: float) -> None:
        """Update the consecutive loss counter after a trade settles.

        A losing trade (pnl < 0) increments the counter.
        A winning trade (pnl >= 0) resets the counter to zero.
        """
        with self._lock:
            entry = self._status.setdefault(strategy, {"consecutive_losses": 0})
            if pnl < 0:
                entry["consecutive_losses"] = entry.get("consecutive_losses", 0) + 1
            else:
                entry["consecutive_losses"] = 0
            self._save_status()

    def check_feed_health(
        self, strategy: str, account_id: str, feed_age_seconds: float
    ) -> dict:
        """Check whether the price feed is fresh enough to trade safely.

        If feed_age_seconds > FEED_STALE_THRESHOLD_SECONDS → PAUSE_SESSION.
        If feed is fresh and strategy was in PAUSE_SESSION due to feed → resume.

        Args:
            strategy: Strategy name.
            account_id: Full account ID.
            feed_age_seconds: Seconds since the last price update.

        Returns:
            Result dict with level and whether trading is allowed.
        """
        if feed_age_seconds > FEED_STALE_THRESHOLD_SECONDS:
            return self._trigger(
                strategy, account_id,
                LEVEL_PAUSE_SESSION, "pause_strategy", "feed_stale",
                None, float(FEED_STALE_THRESHOLD_SECONDS),
            )

        # Feed is fresh — if paused due to staleness, auto-resume
        with self._lock:
            current_level = self._status.get(strategy, {}).get("level", LEVEL_OK)
            current_reason = self._status.get(strategy, {}).get("reason")

        if current_level == LEVEL_PAUSE_SESSION and current_reason == "feed_stale":
            return self._update_level(strategy, account_id, LEVEL_OK)

        return {
            "strategy": strategy,
            "account_id": account_id,
            "level": current_level,
            "action": None,
            "reason": None,
        }

    def check_pre_trade(self, strategy: str) -> dict:
        """Fast synchronous Go/No-Go check using in-memory cached status.

        No disk I/O. Called by the orchestrator before routing each trade signal.

        Args:
            strategy: Strategy name.

        Returns:
            Dict with keys: allowed (bool), level (str), reason (str|None).
        """
        with self._lock:
            entry = self._status.get(strategy, {})
        level = entry.get("level", LEVEL_OK)
        return {
            "allowed": level not in BLOCKED_LEVELS,
            "level": level,
            "reason": entry.get("reason"),
        }

    def reset_daily(self, strategy: str) -> None:
        """Reset daily counters at midnight.

        - consecutive_losses reset to 0
        - PAUSE_DAILY → OK (daily condition has expired)
        - STOP_STRATEGY is permanent — never reset here
        - PAUSE_SESSION is not reset (external condition may still apply)
        """
        with self._lock:
            entry = self._status.get(strategy, {})
            if not entry:
                return
            entry["consecutive_losses"] = 0
            if entry.get("level") == LEVEL_PAUSE_DAILY:
                entry.update({
                    "level": LEVEL_OK,
                    "action": None,
                    "reason": None,
                    "triggered_at": None,
                    "resume_at": None,
                    "drawdown_pct": None,
                    "threshold_pct": None,
                })
            self._save_status()

    def run_once(self) -> list:
        """Tick evaluation: evaluate all registered strategies.

        Called every 5 seconds by the orchestrator.
        Returns list of result dicts for triggered (non-OK/WARNING) events only.
        """
        with self._lock:
            strategies = list(self._status.items())

        results = []
        for strategy, entry in strategies:
            account_id = entry.get("account_id")
            if not account_id:
                continue
            try:
                result = self.evaluate(strategy, account_id)
                if result.get("level") not in (LEVEL_OK, LEVEL_WARNING):
                    results.append(result)
            except FileNotFoundError:
                pass  # account not yet created or archived, skip

        return results
