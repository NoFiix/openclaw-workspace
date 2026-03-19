"""
POLY_FACTORY_ORCHESTRATOR — Central brain of POLY_FACTORY.

Two primary responsibilities:
  1. Signal routing: consume trade:signal events from all strategy agents, run
     each through the 7-filter safety chain (data_quality → microstructure →
     resolution → sizing → kill_switch → risk_guardian → capital_manager), then
     publish trade:validated to the execution router if all filters pass.
  2. Lifecycle management: track strategy lifecycle state (paper →
     awaiting_promotion → live), handle kill-switch events, respond to evaluator
     scores to trigger promotion requests, and run the nightly cycle (reset daily
     counters, surface evaluation results, generate the daily report).

Bus topics consumed:
  - trade:signal
  - risk:kill_switch
  - risk:global_status
  - eval:score_updated
  - promotion:approved
  - promotion:denied
  - signal:resolution_parsed
  - feed:price_update

Bus topics published:
  - trade:validated    — filtered signal ready for execution
  - promotion:request  — promotion eligibility confirmed, awaiting human approval
"""

import logging
import threading
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from core.poly_strategy_account import PolyStrategyAccount
from core.poly_strategy_registry import PolyStrategyRegistry
from execution.poly_order_splitter import PolyOrderSplitter
from risk.poly_capital_manager import PolyCapitalManager
from risk.poly_kelly_sizer import MAX_POSITION_PCT, PolyKellySizer
from risk.poly_kill_switch import PolyKillSwitch
from risk.poly_risk_guardian import PolyRiskGuardian


CONSUMER_ID = "POLY_FACTORY_ORCHESTRATOR"

# Filter thresholds
MIN_EXECUTABILITY_SCORE = 40     # Filter 1 — microstructure gate
MIN_SLIPPAGE_THRESHOLD = 0.03    # Filter 1 — slippage on real order size < 3%
MAX_AMBIGUITY_SCORE = 3          # Filter 2 — ambiguity < 3 (strict, per pipeline §Cycle 4)
MIN_PAPER_TRADES = 50            # promotion eligibility
MIN_PAPER_DAYS = 14              # promotion eligibility
MIN_SCORE_FOR_PROMOTION = 60     # evaluator score threshold

# State file paths (relative to base_path)
SYSTEM_STATE_PATH = "orchestrator/system_state.json"
LIFECYCLE_PATH = "orchestrator/strategy_lifecycle.json"
CYCLE_LOG_PATH = "orchestrator/cycle_log.json"
MARKET_STRUCTURE_PATH = "feeds/market_structure.json"

FILTER_NAMES = [
    "data_quality",
    "microstructure",
    "resolution",
    "sizing",
    "kill_switch",
    "risk_guardian",
    "capital_manager",
]

logger = logging.getLogger("POLY_FACTORY_ORCHESTRATOR")

# Account statuses considered "active" for capital summation and nightly resets
ACTIVE_STATUSES = {"paper_testing", "active"}

# Bus topics the orchestrator consumes
_TOPICS = [
    "trade:signal",
    "risk:kill_switch",
    "risk:global_status",
    "eval:score_updated",
    "promotion:approved",
    "promotion:denied",
    "signal:resolution_parsed",
    "feed:price_update",
]


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PolyFactoryOrchestrator:
    """Central orchestrator: signal routing + strategy lifecycle management."""

    def __init__(
        self,
        base_path="state",
        kill_switch=None,
        risk_guardian=None,
        capital_manager=None,
        global_risk_guard=None,
        evaluator=None,
        decay_detector=None,
        kelly_sizer=None,
    ):
        self.base_path = base_path
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self.store = PolyDataStore(base_path=base_path)
        self.registry = PolyStrategyRegistry(base_path=base_path)
        self.order_splitter = PolyOrderSplitter(base_path=base_path)

        # Injectable dependencies — default to real instances if None
        self.kill_switch = kill_switch or PolyKillSwitch(base_path=base_path)
        self.risk_guardian = risk_guardian or PolyRiskGuardian(base_path=base_path)
        self.capital_manager = capital_manager or PolyCapitalManager(base_path=base_path)
        self.global_risk_guard = global_risk_guard  # optional (no default needed)
        self.evaluator = evaluator
        self.decay_detector = decay_detector
        self.kelly_sizer = kelly_sizer or PolyKellySizer()

        # In-memory caches (updated from bus events, no TTL — latest wins)
        self._price_cache = {}             # market_id → feed:price_update payload
        self._resolution_cache = {}        # market_id → signal:resolution_parsed payload
        self._market_structure_cache = {}  # market_id → structure dict

        self._lock = threading.Lock()

        # Kill switch dedup: log each (strategy, level, reason) only once
        self._ks_logged: set = set()

        # Persisted state loaded at startup
        self._system_state = self._load_system_state()
        self._lifecycle = self._load_lifecycle()

        # Seed resolution cache from disk so Filter 2 works immediately after
        # restart, without waiting for market_analyst to re-publish bus events.
        self._sync_resolution_cache()

        # Register all known strategies with the kill switch so run_once()
        # will evaluate their drawdown on every tick.
        self._register_strategies_with_kill_switch()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _load_system_state(self) -> dict:
        data = self.store.read_json(SYSTEM_STATE_PATH) or {}
        changed = False
        if "global_risk_status" not in data:
            data["global_risk_status"] = "NORMAL"
            changed = True
        if "last_nightly_run" not in data:
            data["last_nightly_run"] = None
            changed = True
        if changed:
            self.store.write_json(SYSTEM_STATE_PATH, data)
        return data

    def _save_system_state(self) -> None:
        self.store.write_json(SYSTEM_STATE_PATH, self._system_state)

    def _load_lifecycle(self) -> dict:
        data = self.store.read_json(LIFECYCLE_PATH) or {}
        if not isinstance(data, dict):
            data = {}
            self.store.write_json(LIFECYCLE_PATH, data)
        return data

    def _save_lifecycle(self) -> None:
        self.store.write_json(LIFECYCLE_PATH, self._lifecycle)

    def _sync_resolution_cache(self) -> None:
        """Populate _resolution_cache from market_analyst's cache file on disk.

        Mirrors the pattern of _sync_price_cache (run_orchestrator.py) so that
        Filter 2 (resolution) has data immediately after a restart instead of
        rejecting every signal with 'no_resolution_data' until new bus events
        arrive.

        Only loads entries that have a valid ``cached_at`` timestamp younger
        than the 48-hour TTL used by PolyMarketAnalyst (CACHE_TTL_SECONDS).
        Legacy entries without ``cached_at`` are ignored.
        """
        from agents.poly_market_analyst import CACHE_TTL_SECONDS

        raw = self.store.read_json("research/resolutions_cache.json") or {}
        now = datetime.now(timezone.utc).timestamp()
        loaded = 0
        for market_id, entry in raw.items():
            cached_at = entry.get("cached_at")
            if cached_at is None:
                continue
            if (now - cached_at) >= CACHE_TTL_SECONDS:
                continue
            # Inject the subset of fields that Filter 2 expects
            self._resolution_cache[market_id] = {
                "market_id": entry.get("market_id", market_id),
                "ambiguity_score": entry.get("ambiguity_score"),
                "unexpected_risk_score": entry.get("unexpected_risk_score"),
                "boolean_condition": entry.get("boolean_condition"),
            }
            loaded += 1
        if loaded:
            import logging
            logging.getLogger("POLY_FACTORY_ORCHESTRATOR").info(
                "_sync_resolution_cache: loaded %d fresh entries from disk", loaded,
            )

    def _append_cycle_log(self, entry: dict) -> None:
        existing = self.store.read_json(CYCLE_LOG_PATH) or []
        if not isinstance(existing, list):
            existing = []
        existing.append(entry)
        self.store.write_json(CYCLE_LOG_PATH, existing)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_lifecycle_entry(self, strategy: str) -> dict:
        """Get or create lifecycle entry for a strategy. Caller holds _lock."""
        if strategy not in self._lifecycle:
            self._lifecycle[strategy] = {
                "lifecycle_phase": "paper",
                "promotion_requested": False,
            }
        return self._lifecycle[strategy]

    def _compute_total_active_capital(self) -> float:
        """Sum capital.current across all accounts with an active status."""
        total = 0.0
        with self._lock:
            strategies = list(self._lifecycle.keys())
        for strategy_name in strategies:
            account_id = f"ACC_{strategy_name}"
            try:
                account = PolyStrategyAccount.load(account_id, self.base_path)
                if account.status in ACTIVE_STATUSES:
                    total += account.data["capital"]["current"]
            except FileNotFoundError:
                pass
        return total

    def _register_strategies_with_kill_switch(self) -> None:
        """Register all lifecycle strategies with the kill switch at startup."""
        with self._lock:
            strategies = list(self._lifecycle.keys())
        for strategy in strategies:
            account_id = f"ACC_{strategy}"
            self.kill_switch.register(strategy, account_id)
        if strategies:
            logger.info(
                "kill_switch: registered %d strategies", len(strategies),
            )

    # ------------------------------------------------------------------
    # 7-Filter chain
    # ------------------------------------------------------------------

    def _run_filter_chain(self, signal_payload: dict) -> dict:
        """Run the 7-filter safety chain on a signal payload.

        Returns:
            {
                "passed": bool,
                "validated_size_eur": float | None,
                "filters_passed": list[str],
                "rejected_by": str | None,
                "reason": str | None,
                "executability_score": int | None,
                "slippage_estimated": float | None,
                "tranches": list | None,   # only when passed=True
                "price": float | None,     # selected price, only when passed=True
            }
        """
        market_id = signal_payload.get("market_id")
        strategy = signal_payload.get("strategy")
        account_id = signal_payload.get("account_id") or f"ACC_{strategy}"
        signal_type = signal_payload.get("signal_type", "")
        direction = signal_payload.get("direction", "BUY_YES")
        confidence = float(signal_payload.get("confidence", 0.0))

        filters_passed = []
        executability_score = None
        slippage_estimated = None
        validated_size = None

        def _reject(filter_name: str, reason: str) -> dict:
            logger.info(
                "SIGNAL_REJECTED | strategy=%s | filter=%s | market_id=%s "
                "| confidence=%.4f | reason=%s",
                strategy, filter_name, market_id, confidence, reason,
            )
            return {
                "passed": False,
                "validated_size_eur": None,
                "filters_passed": filters_passed,
                "rejected_by": filter_name,
                "reason": reason,
                "executability_score": executability_score,
                "slippage_estimated": slippage_estimated,
                "tranches": None,
                "price": None,
            }

        # ------ Filter 0: data_quality ------
        price_payload = self._price_cache.get(market_id)
        if price_payload is None:
            return _reject("data_quality", "no_price_data")
        if price_payload.get("data_status") != "VALID":
            return _reject("data_quality", "data_suspect")
        filters_passed.append("data_quality")

        # ------ Filter 1: microstructure ------
        struct = self._market_structure_cache.get(market_id)
        if struct is None:
            raw = self.store.read_json(MARKET_STRUCTURE_PATH)
            if raw and market_id in raw:
                struct = raw[market_id]
                self._market_structure_cache[market_id] = struct
        if struct is None:
            return _reject("microstructure", "no_structure_data")

        executability_score = struct.get("executability_score", 0)
        if executability_score < MIN_EXECUTABILITY_SCORE:
            return _reject("microstructure", "low_executability_score")

        # Compute slippage on the real max order size (capital × MAX_POSITION_PCT)
        # instead of the legacy fixed $1K reference that is ~33× larger than actual trades.
        try:
            _acct = PolyStrategyAccount.load(account_id, self.base_path)
            _capital = _acct.data["capital"]["current"]
        except (FileNotFoundError, KeyError):
            _capital = 1000.0
        _max_order = _capital * MAX_POSITION_PCT
        _spread_bps = struct.get("spread_bps", 0.0)
        _depth_usd = struct.get("depth_usd", 0.0)
        slippage_estimated = (
            _spread_bps / 10_000 / 2
            + _max_order / max(_depth_usd, _max_order)
        )
        if slippage_estimated >= MIN_SLIPPAGE_THRESHOLD:
            return _reject("microstructure", "high_slippage")
        filters_passed.append("microstructure")

        # ------ Filter 2: resolution (skipped for bundle_arb) ------
        if signal_type != "bundle_arb":
            res = self._resolution_cache.get(market_id)
            if res is None:
                return _reject("resolution", "no_resolution_data")
            if res.get("ambiguity_score", 999) >= MAX_AMBIGUITY_SCORE:
                return _reject("resolution", "high_ambiguity")
        filters_passed.append("resolution")

        # ------ Filter 3: sizing ------
        try:
            account = PolyStrategyAccount.load(account_id, self.base_path)
        except FileNotFoundError:
            return _reject("sizing", "account_not_found")
        current_capital = account.data["capital"]["current"]

        yes_ask = float(price_payload.get("yes_ask", 0.5))
        no_ask = float(price_payload.get("no_ask", 0.5))
        if direction == "BUY_YES":
            selected_price = yes_ask
        elif direction == "BUY_NO":
            selected_price = no_ask
        else:  # BUY_YES_AND_NO
            selected_price = (yes_ask + no_ask) / 2.0

        if signal_type == "bundle_arb":
            # Bundle arbitrage is a near-guaranteed profit (buy YES+NO below 1.0).
            # The Kelly formula assumes a binary uncertain bet; it is not applicable here.
            # Use the signal's suggested size, capped at the per-position hard limit (3%).
            suggested = float(signal_payload.get("suggested_size_eur", 30.0))
            validated_size = min(suggested, current_capital * 0.03)
            if validated_size <= 0:
                return _reject("sizing", "no_capital")
        else:
            # For BUY_NO signals: Kelly needs P(win) = prob_no, not the normalized
            # edge score in "confidence".  Only override when signal_detail.prob_no
            # is present and valid (currently only POLY_NO_SCANNER provides it).
            kelly_confidence = confidence
            if direction == "BUY_NO":
                signal_detail = signal_payload.get("signal_detail") or {}
                prob_no = signal_detail.get("prob_no")
                if isinstance(prob_no, (int, float)) and 0 < prob_no <= 1:
                    kelly_confidence = float(prob_no)

            validated_size = self.kelly_sizer.compute(kelly_confidence, selected_price, current_capital)
            if validated_size <= 0:
                return _reject("sizing", "no_kelly_edge")
        filters_passed.append("sizing")

        # ------ Filter 4: kill_switch ------
        ks_result = self.kill_switch.check_pre_trade(strategy)
        if not ks_result["allowed"]:
            return _reject("kill_switch", ks_result.get("reason") or "kill_switch_blocked")
        filters_passed.append("kill_switch")

        # ------ Filter 5: risk_guardian ------
        category = signal_type or "unknown"
        total_capital = self._compute_total_active_capital()
        rg_result = self.risk_guardian.check(
            proposed_size_eur=validated_size,
            proposed_category=category,
            total_capital_eur=total_capital,
            strategy=strategy,
            strategy_capital=current_capital,
        )
        if not rg_result["allowed"]:
            return _reject("risk_guardian", rg_result.get("blocked_by") or "risk_guardian_blocked")
        filters_passed.append("risk_guardian")

        # ------ Filter 6: capital_manager ------
        cm_result = self.capital_manager.check_capital(account_id, validated_size)
        if not cm_result["allowed"]:
            return _reject("capital_manager", cm_result.get("reason") or "capital_manager_blocked")
        filters_passed.append("capital_manager")

        # All filters passed — compute execution tranches
        depth_usd = float(struct.get("depth_usd", 10_000.0))
        tranches = self.order_splitter.split(validated_size, selected_price, depth_usd)

        return {
            "passed": True,
            "validated_size_eur": validated_size,
            "filters_passed": filters_passed,
            "rejected_by": None,
            "reason": None,
            "executability_score": executability_score,
            "slippage_estimated": slippage_estimated,
            "tranches": tranches,
            "price": selected_price,
        }

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _handle_trade_signal(self, payload: dict) -> dict | None:
        """Handle a trade:signal event. Returns validated payload or None."""
        self.audit.log_event(
            "signal:generated", CONSUMER_ID,
            {
                "market_id": payload.get("market_id"),
                "strategy": payload.get("strategy"),
            },
        )

        result = self._run_filter_chain(payload)

        if not result["passed"]:
            self.audit.log_event(
                "signal:rejected", CONSUMER_ID,
                {
                    "market_id": payload.get("market_id"),
                    "strategy": payload.get("strategy"),
                    "rejected_by": result["rejected_by"],
                    "reason": result["reason"],
                },
            )
            return None

        strategy = payload.get("strategy")
        account_id = payload.get("account_id") or f"ACC_{strategy}"
        validated_payload = {
            "strategy": strategy,
            "account_id": account_id,
            "market_id": payload.get("market_id"),
            "platform": payload.get("platform", "polymarket"),
            "direction": payload.get("direction", "BUY_YES"),
            "validated_size_eur": result["validated_size_eur"],
            "tranches": result["tranches"],
            "filters_passed": result["filters_passed"],
            "executability_score": result["executability_score"],
            "slippage_estimated": result["slippage_estimated"],
            "expected_fill_price": (payload.get("signal_detail") or {}).get("yes_ask")
                                or (payload.get("signal_detail") or {}).get("no_ask"),
        }

        self.bus.publish("trade:validated", CONSUMER_ID, validated_payload)
        self.audit.log_event("signal:validated", CONSUMER_ID, validated_payload)
        return validated_payload

    def _handle_kill_switch(self, payload: dict) -> None:
        """Handle a risk:kill_switch event — update lifecycle and registry."""
        action = payload.get("action")
        strategy = payload.get("strategy")
        if not strategy:
            return

        with self._lock:
            entry = self._get_lifecycle_entry(strategy)
            if action == "pause_strategy":
                entry["lifecycle_phase"] = "paused"
                self._save_lifecycle()
            elif action == "stop_strategy":
                entry["lifecycle_phase"] = "stopped"
                self._save_lifecycle()

        if action == "pause_strategy":
            self.audit.log_event(
                "lifecycle:paused", CONSUMER_ID,
                {"strategy": strategy, "action": action},
            )
        elif action == "stop_strategy":
            try:
                self.registry.update_status(strategy, "stopped")
            except ValueError:
                pass  # strategy not in registry — not an error
            self.audit.log_event(
                "lifecycle:stopped", CONSUMER_ID,
                {"strategy": strategy, "action": action},
            )

    def _handle_global_risk(self, payload: dict) -> None:
        """Handle a risk:global_status event."""
        self._system_state["global_risk_status"] = payload.get("status")
        self._save_system_state()

    def _handle_eval_score(self, payload: dict) -> bool:
        """Handle an eval:score_updated event.

        Returns True if a promotion:request was published.
        """
        strategy = payload.get("strategy")
        score = payload.get("score", 0)
        verdict = payload.get("verdict", "")

        if not strategy:
            return False

        # Eligibility gate (fast checks first, no I/O)
        if score < MIN_SCORE_FOR_PROMOTION:
            return False
        if verdict in ("RETIRE", "DECLINING"):
            return False
        if self._system_state.get("global_risk_status") != "NORMAL":
            return False

        with self._lock:
            entry = self._get_lifecycle_entry(strategy)
            if entry.get("promotion_requested"):
                return False

        # Load account for trade count and paper_days (I/O outside lock)
        account_id = f"ACC_{strategy}"
        try:
            account = PolyStrategyAccount.load(account_id, self.base_path)
        except FileNotFoundError:
            return False

        account_data = account.data
        total_trades = account_data["performance"]["total_trades"]
        if total_trades < MIN_PAPER_TRADES:
            return False

        paper_started_str = account_data["performance"].get("paper_started")
        paper_days = 0
        if paper_started_str:
            try:
                paper_started = datetime.fromisoformat(
                    paper_started_str.replace("Z", "+00:00")
                )
                paper_days = (datetime.now(timezone.utc) - paper_started).days
            except (ValueError, AttributeError):
                paper_days = 0

        if paper_days < MIN_PAPER_DAYS:
            return False

        # All checks passed — publish promotion request
        promo_payload = {
            "strategy": strategy,
            "score": score,
            "total_trades": total_trades,
            "paper_days": paper_days,
        }
        self.bus.publish("promotion:request", CONSUMER_ID, promo_payload)

        with self._lock:
            entry = self._get_lifecycle_entry(strategy)
            entry["promotion_requested"] = True
            self._save_lifecycle()

        self.audit.log_event("promotion:request_published", CONSUMER_ID, promo_payload)
        return True

    def _handle_promotion_result(self, topic: str, payload: dict) -> None:
        """Handle promotion:approved or promotion:denied events."""
        strategy = payload.get("strategy")
        if not strategy:
            return

        with self._lock:
            entry = self._get_lifecycle_entry(strategy)
            if topic == "promotion:approved":
                entry["lifecycle_phase"] = "awaiting_live"
                entry["promotion_requested"] = False
                self._save_lifecycle()
            elif topic == "promotion:denied":
                entry["promotion_requested"] = False
                self._save_lifecycle()

        if topic == "promotion:approved":
            self.audit.log_event(
                "lifecycle:awaiting_live", CONSUMER_ID,
                {"strategy": strategy},
            )
        elif topic == "promotion:denied":
            self.audit.log_event(
                "promotion:denied", CONSUMER_ID,
                {"strategy": strategy, "reason": payload.get("reason")},
            )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_once(self) -> list:
        """Poll all 8 topics, dispatch each event to its handler, ack all events.

        Returns:
            List of action dicts — one per event processed.
        """
        # Evaluate kill switch for all registered strategies BEFORE
        # processing any bus events.  This ensures check_pre_trade()
        # returns up-to-date status when filtering trade:signal events.
        try:
            ks_results = self.kill_switch.run_once()
            for r in ks_results:
                key = (r.get("strategy"), r.get("level"), r.get("reason"))
                if key not in self._ks_logged:
                    self._ks_logged.add(key)
                    logger.info(
                        "KILL_SWITCH_TRIGGERED | strategy=%s | level=%s | reason=%s | drawdown=%.2f%%",
                        r.get("strategy"), r.get("level"),
                        r.get("reason"), r.get("drawdown_pct", 0),
                    )
        except Exception:
            logger.exception("kill_switch.run_once() failed")

        events = self.bus.poll(CONSUMER_ID, topics=_TOPICS)
        actions = []

        for evt in events:
            topic = evt.get("topic")
            payload = evt.get("payload", {})
            event_id = evt.get("event_id")

            if topic == "trade:signal":
                result = self._handle_trade_signal(payload)
                if result is not None:
                    actions.append({"type": "signal_validated", "payload": result})
                else:
                    actions.append({"type": "signal_rejected"})

            elif topic == "risk:kill_switch":
                self._handle_kill_switch(payload)
                actions.append({"type": "kill_switch_handled", "action": payload.get("action")})

            elif topic == "risk:global_status":
                self._handle_global_risk(payload)
                actions.append({"type": "global_risk_updated", "status": payload.get("status")})

            elif topic == "eval:score_updated":
                promoted = self._handle_eval_score(payload)
                actions.append({"type": "eval_score_handled", "promotion_requested": promoted})

            elif topic in ("promotion:approved", "promotion:denied"):
                self._handle_promotion_result(topic, payload)
                actions.append({"type": "promotion_result_handled", "topic": topic})

            elif topic == "signal:resolution_parsed":
                market_id = payload.get("market_id")
                if market_id:
                    self._resolution_cache[market_id] = payload
                    # Close all open positions on this resolved market
                    closed = self.risk_guardian.close_positions_for_market(market_id)
                    if closed > 0:
                        logger.info("Closed %d position(s) for resolved market %s", closed, market_id)
                actions.append({"type": "resolution_cached", "market_id": market_id})

            elif topic == "feed:price_update":
                market_id = payload.get("market_id")
                if market_id:
                    self._price_cache[market_id] = payload
                actions.append({"type": "price_cached", "market_id": market_id})

            self.bus.ack(CONSUMER_ID, event_id)

        # Cycle summary for signal processing
        n_validated = sum(1 for a in actions if a["type"] == "signal_validated")
        n_rejected = sum(1 for a in actions if a["type"] == "signal_rejected")
        if n_validated + n_rejected > 0:
            logger.info(
                "CYCLE_SUMMARY | signals_evaluated=%d | passed=%d | rejected=%d",
                n_validated + n_rejected, n_validated, n_rejected,
            )

        return actions

    # ------------------------------------------------------------------
    # Nightly cycle
    # ------------------------------------------------------------------

    def run_nightly(self) -> dict:
        """Run the nightly maintenance cycle.

        Steps:
          1. Reset daily kill switch counters for all lifecycle strategies.
          2. Reset daily account P&L for all active accounts.
          3. Run evaluator if injected.
          4. Run decay detector if injected.
          5. Build and log report.
          6. Update system_state.last_nightly_run.
          7. Audit nightly:cycle_completed.
          8. Compact the event bus (remove acked events from pending_events.jsonl).

        Returns:
            Report dict: {date, strategies_evaluated, promotions_pending,
                          cycle_completed_at}
        """
        with self._lock:
            lifecycle_strategies = list(self._lifecycle.keys())

        # 1. Reset daily kill switch counters
        for strategy in lifecycle_strategies:
            self.kill_switch.reset_daily(strategy)

        # 2. Reset daily account P&L (paper_testing or active accounts only)
        for strategy_name in lifecycle_strategies:
            account_id = f"ACC_{strategy_name}"
            try:
                account = PolyStrategyAccount.load(account_id, self.base_path)
                if account.status in ACTIVE_STATUSES:
                    account.reset_daily()
            except FileNotFoundError:
                pass

        # 3. Run evaluator if injected
        strategies_evaluated = []
        if self.evaluator is not None:
            self.evaluator.run_once(lifecycle_strategies)
            strategies_evaluated = lifecycle_strategies[:]

        # 4. Run decay detector if injected
        if self.decay_detector is not None:
            self.decay_detector.run_once(lifecycle_strategies)

        # 5. Collect pending promotions
        promotions_pending = []
        with self._lock:
            for strategy, lc_entry in self._lifecycle.items():
                if lc_entry.get("promotion_requested"):
                    promotions_pending.append(strategy)

        # 6. Build report and append to cycle log
        cycle_completed_at = _now_utc()
        report = {
            "date": _now_utc(),
            "strategies_evaluated": strategies_evaluated,
            "promotions_pending": promotions_pending,
            "cycle_completed_at": cycle_completed_at,
        }
        self._append_cycle_log(report)

        # 7. Update system state
        self._system_state["last_nightly_run"] = cycle_completed_at
        self._save_system_state()

        # 8. Audit
        self.audit.log_event("nightly:cycle_completed", CONSUMER_ID, report)

        # 9. Compact the event bus (remove acked events to prevent unbounded growth)
        self.bus.compact()

        return report
