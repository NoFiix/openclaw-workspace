"""
POLY_STRATEGY_PROMOTION_GATE — Safety-critical decision point for paper → live promotion.

Receives promotion:request events from the orchestrator, runs 10 sequential checks,
and publishes promotion:approved or promotion:denied on the bus.

10 checks (in order):
  1. registry       — strategy exists in registry with status "awaiting_promotion"
  2. account_metrics — ≥ 50 paper trades AND ≥ 14 paper days
  3. eval_score     — evaluator score ≥ 60
  4. decay          — no active SERIOUS or CRITICAL decay alert
  5. approval_exists — human approval JSON present in state/human/approvals.json
  6. approval_expiry — approval less than 7 days old
  7. approval_limits — approval contains capital_max, max_per_trade, kill_switch
  8. global_risk_status — system-wide risk status is NORMAL
  9. global_risk_headroom — total_loss + 1 000€ worst-case < 4 000€
 10. wallet_balance — USDC.e wallet balance ≥ 1 000€

CRITICAL — Gate DECIDES. Capital Manager EXECUTES.
This class NEVER creates strategy accounts. Account creation is exclusively
the responsibility of POLY_CAPITAL_MANAGER (triggered by promotion:approved).

Bus topics consumed : promotion:request
Bus topics published: promotion:approved, promotion:denied
"""

from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_strategy_account import PolyStrategyAccount
from core.poly_strategy_registry import PolyStrategyRegistry


CONSUMER_ID = "POLY_STRATEGY_PROMOTION_GATE"

# Promotion eligibility thresholds
MIN_PAPER_TRADES         = 50
MIN_PAPER_DAYS           = 14
MIN_EVAL_SCORE           = 60
APPROVAL_EXPIRY_DAYS     = 7
WORST_CASE_PROMOTION_EUR = 1000.0   # capital injected per live strategy account
GLOBAL_LOSS_CEILING_EUR  = 4000.0   # hard ceiling from POLY_GLOBAL_RISK_GUARD
MIN_WALLET_USDC_EUR      = 1000.0   # minimum USDC.e balance to fund one account

REQUIRED_APPROVAL_FIELDS = {"capital_max", "max_per_trade", "kill_switch"}
BLOCKED_DECAY_SEVERITIES = {"SERIOUS", "CRITICAL"}

# "awaiting_human" in the implementation plan corresponds to "awaiting_promotion"
# in the actual PolyStrategyRegistry implementation.
REGISTRY_PROMOTABLE_STATUS = "awaiting_promotion"

# State files read by the gate (never written — gate is read-only w.r.t. state)
SCORES_FILE       = "evaluation/strategy_scores.json"
DECAY_ALERTS_FILE = "evaluation/decay_alerts.json"
APPROVALS_FILE    = "human/approvals.json"
GLOBAL_RISK_FILE  = "risk/global_risk_state.json"
WALLET_FILE       = "feeds/wallet_raw_positions.json"

CHECK_NAMES = [
    "registry",              # 1
    "account_metrics",       # 2
    "eval_score",            # 3
    "decay",                 # 4
    "approval_exists",       # 5
    "approval_expiry",       # 6
    "approval_limits",       # 7
    "global_risk_status",    # 8
    "global_risk_headroom",  # 9
    "wallet_balance",        # 10
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts_str: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp string (e.g. '2026-03-01T10:00:00Z')."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


class PolyStrategyPromotionGate:
    """10-check promotion gate: paper → live. Decides, never executes."""

    def __init__(self, base_path: str = "state"):
        self.base_path = base_path
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self.store = PolyDataStore(base_path=base_path)
        self.registry = PolyStrategyRegistry(base_path=base_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _deny(
        self,
        checks_passed: list,
        check_name: str,
        reason: str,
        strategy: str,
    ) -> dict:
        """Build a denial result dict."""
        return {
            "approved": False,
            "strategy": strategy,
            "checks_passed": checks_passed,
            "check_failed": check_name,
            "reason": reason,
            "approval_json": None,
        }

    # ------------------------------------------------------------------
    # 10-check chain
    # ------------------------------------------------------------------

    def _run_checks(self, strategy: str) -> dict:
        """Run all 10 promotion checks in order. Pure logic — no bus/audit side effects.

        Stops at the first failing check and returns the denial reason.

        Returns:
            {
                "approved": bool,
                "strategy": str,
                "checks_passed": list[str],
                "check_failed": str | None,
                "reason": str | None,
                "approval_json": dict | None,
            }
        """
        passed = []

        def deny(check_name: str, reason: str) -> dict:
            return self._deny(passed, check_name, reason, strategy)

        # ------ Check 1: registry ------
        entry = self.registry.get(strategy)
        if entry is None:
            return deny("registry", "strategy_not_registered")
        if entry["status"] != REGISTRY_PROMOTABLE_STATUS:
            return deny("registry", "wrong_registry_status")
        passed.append("registry")

        # ------ Check 2: account_metrics ------
        account_id = f"ACC_{strategy}"
        try:
            account = PolyStrategyAccount.load(account_id, self.base_path)
        except FileNotFoundError:
            return deny("account_metrics", "account_not_found")

        account_data = account.data
        total_trades = account_data["performance"]["total_trades"]
        if total_trades < MIN_PAPER_TRADES:
            return deny("account_metrics", "insufficient_trades")

        paper_started_str = account_data["performance"].get("paper_started")
        paper_days = 0
        if paper_started_str:
            try:
                paper_started = _parse_ts(paper_started_str)
                paper_days = (_now_utc() - paper_started).days
            except (ValueError, AttributeError):
                paper_days = 0
        if paper_days < MIN_PAPER_DAYS:
            return deny("account_metrics", "insufficient_paper_days")
        passed.append("account_metrics")

        # ------ Check 3: eval_score ------
        scores = self.store.read_json(SCORES_FILE) or {}
        score = scores.get(strategy, {}).get("score", 0)
        if score < MIN_EVAL_SCORE:
            return deny("eval_score", "eval_score_too_low")
        passed.append("eval_score")

        # ------ Check 4: decay ------
        alerts = self.store.read_json(DECAY_ALERTS_FILE) or {}
        severity = alerts.get(strategy, {}).get("severity", "HEALTHY")
        if severity in BLOCKED_DECAY_SEVERITIES:
            return deny("decay", "active_decay_alert")
        passed.append("decay")

        # ------ Check 5: approval_exists ------
        approvals = self.store.read_json(APPROVALS_FILE) or {}
        approval = approvals.get(strategy)
        if approval is None:
            return deny("approval_exists", "no_human_approval")
        passed.append("approval_exists")

        # ------ Check 6: approval_expiry ------
        approved_at_str = approval.get("approved_at", "")
        try:
            approved_at = _parse_ts(approved_at_str)
            age_days = (_now_utc() - approved_at).days
        except (ValueError, AttributeError):
            age_days = APPROVAL_EXPIRY_DAYS  # treat unparseable as expired
        if age_days >= APPROVAL_EXPIRY_DAYS:
            return deny("approval_expiry", "approval_expired")
        passed.append("approval_expiry")

        # ------ Check 7: approval_limits ------
        for field in REQUIRED_APPROVAL_FIELDS:
            if field not in approval:
                return deny("approval_limits", "approval_missing_limits")
        passed.append("approval_limits")

        # ------ Check 8: global_risk_status ------
        global_state = self.store.read_json(GLOBAL_RISK_FILE) or {}
        risk_status = global_state.get("status", "NORMAL")
        if risk_status != "NORMAL":
            return deny("global_risk_status", "global_risk_not_normal")
        passed.append("global_risk_status")

        # ------ Check 9: global_risk_headroom ------
        total_loss_eur = float(global_state.get("total_loss_eur", 0.0))
        if total_loss_eur + WORST_CASE_PROMOTION_EUR >= GLOBAL_LOSS_CEILING_EUR:
            return deny("global_risk_headroom", "global_risk_headroom_insufficient")
        passed.append("global_risk_headroom")

        # ------ Check 10: wallet_balance ------
        wallet = self.store.read_json(WALLET_FILE) or {}
        usdc_balance = float(wallet.get("USDC.e", 0.0))
        if usdc_balance < MIN_WALLET_USDC_EUR:
            return deny("wallet_balance", "insufficient_wallet_balance")
        passed.append("wallet_balance")

        # All 10 checks passed
        return {
            "approved": True,
            "strategy": strategy,
            "checks_passed": passed,
            "check_failed": None,
            "reason": None,
            "approval_json": approval,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, strategy: str) -> dict:
        """Run 10 checks and publish promotion:approved or promotion:denied.

        The gate DECIDES only — it never creates accounts.
        Account creation is triggered by promotion:approved consumed by
        POLY_CAPITAL_MANAGER.

        Args:
            strategy: Strategy name (e.g. "POLY_ARB_SCANNER").

        Returns:
            Result dict from _run_checks(), same dict published on the bus.
        """
        result = self._run_checks(strategy)

        if result["approved"]:
            self.bus.publish("promotion:approved", CONSUMER_ID, result)
            self.audit.log_event("promotion:approved", CONSUMER_ID, result)
        else:
            self.bus.publish("promotion:denied", CONSUMER_ID, result)
            self.audit.log_event("promotion:denied", CONSUMER_ID, result)

        return result

    def run_once(self) -> list:
        """Poll promotion:request events and evaluate each strategy.

        All events are acked after processing regardless of outcome.

        Returns:
            List of result dicts — one per promotion:request event processed.
        """
        events = self.bus.poll(CONSUMER_ID, topics=["promotion:request"])
        results = []

        for evt in events:
            payload = evt.get("payload", {})
            strategy = payload.get("strategy")
            if strategy:
                result = self.evaluate(strategy)
                results.append(result)
            self.bus.ack(CONSUMER_ID, evt["event_id"])

        return results
