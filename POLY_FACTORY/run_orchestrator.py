"""
POLY_FACTORY — Orchestrator entry point.

Usage:
    python run_orchestrator.py [--mode paper|live]

Runs the central orchestrator in a polling loop:
  - run_once() every POLL_INTERVAL_S seconds (bus routing)
  - run_nightly() once per day at midnight UTC

AgentScheduler calls all data feeds, C2 signal agents, strategy agents,
execution router, and paper engine at their configured intervals.
"""

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

# Ensure repo root is on the path when invoked directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env BEFORE any agent imports that read os.environ at module level
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass  # python-dotenv not installed — rely on ecosystem.config.cjs env injection

from core.poly_factory_orchestrator import PolyFactoryOrchestrator
from core.poly_strategy_account import PolyStrategyAccount
from core.poly_strategy_registry import PolyStrategyRegistry
from risk.poly_risk_guardian import PolyRiskGuardian

# ---------------------------------------------------------------------------
# Agent imports
# ---------------------------------------------------------------------------

from connectors.connector_polymarket import ConnectorPolymarket
from agents.poly_binance_feed import PolyBinanceFeed
from agents.poly_noaa_feed import PolyNoaaFeed
from agents.poly_wallet_feed import PolyWalletFeed
from agents.poly_market_structure_analyzer import PolyMarketStructureAnalyzer
from agents.poly_binance_signals import PolyBinanceSignals
from agents.poly_wallet_tracker import PolyWalletTracker
from agents.poly_data_validator import PolyDataValidator
from agents.poly_market_funnel import PolyMarketFunnel
from agents.poly_market_analyst import PolyMarketAnalyst
from strategies.poly_arb_scanner import PolyArbScanner
from strategies.poly_weather_arb import PolyWeatherArb
from strategies.poly_latency_arb import PolyLatencyArb
from strategies.poly_brownian_sniper import PolyBrownianSniper
from strategies.poly_pair_cost import PolyPairCost
from strategies.poly_opp_scorer import PolyOppScorer
from strategies.poly_no_scanner import PolyNoScanner
from strategies.poly_convergence_strat import PolyConvergenceStrat
from strategies.poly_news_strat import PolyNewsStrat
from agents.poly_heartbeat import PolyHeartbeat
from agents.poly_system_monitor import PolySystemMonitor
from execution.poly_execution_router import PolyExecutionRouter
from execution.poly_paper_execution_engine import PolyPaperExecutionEngine

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

POLL_INTERVAL_S = 2.0   # main loop cadence (1-5s per architecture spec)
BASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")

# Strategies that must have accounts and registry entries before the main loop starts.
# Each tuple: (strategy_name, category)
STRATEGIES = [
    ("POLY_ARB_SCANNER",      "arbitrage"),
    ("POLY_WEATHER_ARB",      "arbitrage"),
    ("POLY_LATENCY_ARB",      "arbitrage"),
    ("POLY_BROWNIAN_SNIPER",  "momentum"),
    ("POLY_PAIR_COST",        "cost"),
    ("POLY_OPP_SCORER",       "scoring"),
    ("POLY_NO_SCANNER",       "directional"),
    ("POLY_CONVERGENCE_STRAT","convergence"),
    ("POLY_NEWS_STRAT",       "news"),
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("POLY_ORCHESTRATOR")

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Signal %s received — shutting down gracefully.", signum)
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

# ---------------------------------------------------------------------------
# AgentScheduler
# ---------------------------------------------------------------------------


def _bootstrap_strategies(base_path):
    """Ensure every strategy has a registry entry, a paper-testing account,
    and a lifecycle entry in the orchestrator's lifecycle file.

    Safe to call on every startup: all operations are idempotent (catch ValueError
    when an entry already exists).

    The lifecycle file must be pre-populated so that PolyFactoryOrchestrator.
    _compute_total_active_capital() can sum accounts and the risk_guardian sees
    a non-zero total_capital_eur (otherwise it treats any trade as 100% exposure
    and blocks everything with "max_exposure").
    """
    from core.poly_data_store import PolyDataStore
    store = PolyDataStore(base_path=base_path)

    registry = PolyStrategyRegistry(base_path=base_path)
    for name, category in STRATEGIES:
        # Registry entry
        try:
            registry.register(
                name=name,
                category=category,
                platform="polymarket",
                parameters={},
            )
            registry.update_status(name, "paper_testing")
            logger.info("bootstrap: registered strategy %s", name)
        except ValueError:
            pass  # already registered — fine

        # Strategy account
        try:
            PolyStrategyAccount.create(
                strategy=name,
                platform="polymarket",
                base_path=base_path,
            )
            logger.info("bootstrap: created account ACC_%s", name)
        except ValueError:
            pass  # account already exists — fine

    # Lifecycle file: ensure every strategy has an entry so the orchestrator
    # can compute total_active_capital (needed by the risk_guardian filter).
    lifecycle = store.read_json("orchestrator/strategy_lifecycle.json") or {}
    changed = False
    for name, _category in STRATEGIES:
        if name not in lifecycle:
            lifecycle[name] = {"lifecycle_phase": "paper", "promotion_requested": False}
            changed = True
    if changed:
        store.write_json("orchestrator/strategy_lifecycle.json", lifecycle)
        logger.info("bootstrap: lifecycle file initialised for %d strategies", len(lifecycle))


class AgentScheduler:
    """Calls each agent at its configured interval within the main loop.

    Agents run sequentially. Each agent's exception is caught independently
    so one failing agent never blocks the rest.

    Execution order per tick (dependency order):
      C1 feeds   → C2 signal agents → C3 strategies → execution chain → system
    """

    def __init__(self, base_path, risk_guardian=None):
        # Each entry: (label, instance, interval_s, method_name)
        # Shared connector instance: poll_markets (slow) and poll_prices (fast)
        # must share the same _prices_cache to avoid stale data.
        _connector = ConnectorPolymarket(base_path=base_path)

        self._schedule = [
            # ── C1: Data feeds ──────────────────────────────────────────────
            # Connector: market list refresh (slow path, 300s)
            ("connector",        _connector,                                     300, "poll_markets"),
            # Connector: price refresh (fast path, 30s, single batch write)
            ("connector_prices", _connector,                                      30, "poll_prices"),
            # Binance REST snapshot → feed:binance_update + binance_raw.json
            ("binance_feed", PolyBinanceFeed(base_path=base_path),               30,  "poll_once"),
            # NOAA weather forecast → feed:noaa_update + noaa_forecasts.json
            ("noaa_feed",    PolyNoaaFeed(base_path=base_path),                  120, "poll_once"),
            # Polymarket wallet positions → feed:wallet_update (10 min: positions require auth)
            ("wallet_feed",  PolyWalletFeed(base_path=base_path),                600, "poll_once"),

            # ── C1b: Funnel (runs after connector, before signal processors) ──
            # Reads active_markets_full.json → writes active_markets.json (LLM shortlist)
            ("funnel",       PolyMarketFunnel(base_path=base_path),              300, "run_once"),

            # ── C2: Signal processors ────────────────────────────────────────
            # Reads polymarket_prices.json → publishes signal:market_structure
            ("msa",          PolyMarketStructureAnalyzer(base_path=base_path),   30,  "run_once"),
            # Reads binance_raw.json → publishes signal:binance_score
            ("binance_sig",  PolyBinanceSignals(base_path=base_path),            10,  "run_once"),
            # Polls feed:wallet_update → publishes signal:wallet_convergence
            ("wallet_track", PolyWalletTracker(base_path=base_path),             60,  "run_once"),
            # Reads all feed state files → publishes data:validation_failed
            ("data_val",     PolyDataValidator(base_path=base_path),             10,  "run_once"),
            # Reads active_markets.json → publishes signal:resolution_parsed (LLM, cached)
            ("mkt_analyst",  PolyMarketAnalyst(base_path=base_path),             900, "run_once"),

            # ── C3: Strategy agents (poll bus → publish trade:signal) ────────
            ("arb_scanner",  PolyArbScanner(base_path=base_path),                5,   "run_once"),
            ("weather_arb",  PolyWeatherArb(base_path=base_path),                60,  "run_once"),
            ("latency_arb",  PolyLatencyArb(base_path=base_path),                5,   "run_once"),
            ("brownian",     PolyBrownianSniper(base_path=base_path),            5,   "run_once"),
            ("pair_cost",    PolyPairCost(base_path=base_path),                  5,   "run_once"),
            ("opp_scorer",   PolyOppScorer(base_path=base_path),                 30,  "run_once"),
            ("no_scanner",   PolyNoScanner(base_path=base_path),                 30,  "run_once"),
            ("convergence",  PolyConvergenceStrat(base_path=base_path),          30,  "run_once"),
            ("news_strat",   PolyNewsStrat(base_path=base_path),                 30,  "run_once"),

            # ── Execution chain (trade:validated → execute:paper → fill) ─────
            # Routes trade:validated → execute:paper or execute:live
            ("exec_router",  PolyExecutionRouter(base_path=base_path),           2,   "run_once"),
            # Simulates fill, writes paper_trades_log.jsonl
            # risk_guardian is injected to share the same instance as the orchestrator
            ("paper_engine", PolyPaperExecutionEngine(base_path=base_path, risk_guardian=risk_guardian),  2,  "run_once"),

            # ── System agents ────────────────────────────────────────────────
            ("heartbeat",    PolyHeartbeat(base_path=base_path),                 300, "run_once"),
            ("sys_monitor",  PolySystemMonitor(base_path=base_path),             300, "run_once"),
        ]
        self._last_run = {label: 0.0 for label, _, _, _ in self._schedule}

        # Register all monitored agents with the heartbeat at startup.
        # System agents (heartbeat, sys_monitor) are not monitored by heartbeat.
        self._heartbeat = next(
            inst for lbl, inst, _, _ in self._schedule if lbl == "heartbeat"
        )
        for label, _agent, interval, _method in self._schedule:
            if label not in ("heartbeat", "sys_monitor"):
                self._heartbeat.register(label, expected_freq_s=float(interval))

    def tick(self):
        """Run all agents whose interval has elapsed since their last call."""
        now = time.monotonic()
        for label, agent, interval, method in self._schedule:
            if now - self._last_run[label] >= interval:
                try:
                    getattr(agent, method)()
                    # Ping heartbeat on successful execution so liveness is tracked
                    if label not in ("heartbeat", "sys_monitor"):
                        self._heartbeat.ping(label)
                except Exception:
                    logger.exception("Agent %s (%s) failed", label, method)
                self._last_run[label] = now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_portfolio_state(base_path, risk_guardian):
    """Seed portfolio_state.json from paper_trades_log.jsonl if needed.

    Runs once at startup. Idempotent: does nothing if the file already
    contains valid data with open_positions.

    This covers trades executed before add_position() was wired into the
    paper engine (pre-2026-03-18). Once the system has been running with
    the shared risk_guardian for a while, this seed becomes a no-op.
    """
    import json
    from core.poly_data_store import PolyDataStore

    store = PolyDataStore(base_path=base_path)
    state = risk_guardian.get_state()

    # Guard: if state already has positions, skip seed entirely
    if state.get("open_positions"):
        logger.info("seed: portfolio_state.json already has %d positions — skipping",
                     len(state["open_positions"]))
        return

    # Read paper trades log
    trades_path = os.path.join(base_path, "trading", "paper_trades_log.jsonl")
    if not os.path.exists(trades_path):
        logger.info("seed: no paper_trades_log.jsonl — nothing to seed")
        return

    # Load known strategy names from accounts for validation
    accounts_dir = os.path.join(base_path, "accounts")
    known_strategies = set()
    if os.path.isdir(accounts_dir):
        for fname in os.listdir(accounts_dir):
            if fname.startswith("ACC_POLY_") and fname.endswith(".json"):
                # ACC_POLY_OPP_SCORER.json → POLY_OPP_SCORER
                known_strategies.add(fname[4:-5])

    # Parse trades line by line, tolerating invalid lines
    trades = []
    ignored = 0
    with open(trades_path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("seed: line %d — invalid JSON, ignored", lineno)
                ignored += 1
                continue
            # Validate required fields
            strategy = t.get("strategy")
            market_id = t.get("market_id")
            size_eur = t.get("size_eur")
            if not strategy or not market_id or size_eur is None:
                logger.warning("seed: line %d — missing required fields, ignored", lineno)
                ignored += 1
                continue
            # Validate strategy name matches known accounts
            if known_strategies and strategy not in known_strategies:
                logger.warning(
                    "seed: line %d — strategy '%s' not in known accounts, ignored",
                    lineno, strategy,
                )
                ignored += 1
                continue
            trades.append(t)

    if not trades:
        logger.info("seed: no valid trades found — nothing to seed")
        return

    # Group by (strategy, market_id), sum size_eur
    grouped = {}
    for t in trades:
        key = (t["strategy"], t["market_id"])
        if key not in grouped:
            grouped[key] = {
                "strategy": t["strategy"],
                "market_id": t["market_id"],
                "size_eur": 0.0,
                "category": t.get("category", "unknown"),
                "opened_at": None,
            }
        grouped[key]["size_eur"] += float(t["size_eur"])
        # Keep earliest trade_id timestamp as opened_at
        trade_id = t.get("trade_id", "")
        m = None
        if trade_id:
            import re
            m = re.match(r"TRD_(\d{4})(\d{2})(\d{2})_", trade_id)
        if m:
            ts = f"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00Z"
            if grouped[key]["opened_at"] is None or ts < grouped[key]["opened_at"]:
                grouped[key]["opened_at"] = ts

    # Inject positions via add_position (uses the shared instance, writes to disk)
    for pos in grouped.values():
        risk_guardian.add_position(
            strategy=pos["strategy"],
            market_id=pos["market_id"],
            size_eur=pos["size_eur"],
            category=pos["category"],
        )

    # Patch opened_at to historical dates (add_position always writes _now_utc).
    # Done in a single pass after all positions are added, under the guardian's lock.
    with risk_guardian._lock:
        for p in risk_guardian._state.get("open_positions", []):
            key = (p["strategy"], p["market_id"])
            if key in grouped and grouped[key]["opened_at"]:
                p["opened_at"] = grouped[key]["opened_at"]
        risk_guardian._save_state()

    logger.info(
        "seed: portfolio_state.json seeded from %d historical trades → %d positions%s",
        len(trades), len(grouped),
        f" ({ignored} entries ignored)" if ignored else "",
    )


def _should_run_nightly(last_nightly_date):
    """Return True if today's nightly cycle hasn't run yet."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return last_nightly_date != today


def _sync_price_cache(orchestrator):
    """Populate orchestrator._price_cache from the connector's state file.

    The connector writes feeds/polymarket_prices.json every 300s.  Strategies
    that poll feed:price_update from the bus ack those events before the
    orchestrator can see them (global-ack bus model).  Reading from disk
    guarantees the orchestrator always has the latest prices regardless of
    bus ack order, so filter 0 (data_quality) passes when price data exists.
    """
    raw = orchestrator.store.read_json("feeds/polymarket_prices.json") or {}
    for market_id, payload in raw.items():
        orchestrator._price_cache[market_id] = payload


def _last_nightly_date(orchestrator):
    run_ts = orchestrator._system_state.get("last_nightly_run")
    if run_ts is None:
        return None
    try:
        dt = datetime.fromisoformat(run_ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="POLY_FACTORY orchestrator")
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default=os.environ.get("POLY_MODE", "paper"),
        help="Execution mode (paper or live). Default: paper.",
    )
    args = parser.parse_args()

    # Propagate mode to env so execution router and other agents can read it
    os.environ["POLY_MODE"] = args.mode

    logger.info("Starting POLY_FACTORY orchestrator | mode=%s | base=%s", args.mode, BASE_PATH)

    # Ensure all strategy accounts and registry entries exist before the main loop
    _bootstrap_strategies(BASE_PATH)

    # Single shared RiskGuardian instance — used by both orchestrator (check,
    # close_positions_for_market) and paper_engine (add_position).
    # Prevents state divergence between two independent in-memory copies.
    risk_guardian = PolyRiskGuardian(base_path=BASE_PATH)

    # Seed portfolio_state.json from historical trades if it doesn't exist yet.
    # Idempotent: no-op if the file already contains valid data.
    _seed_portfolio_state(BASE_PATH, risk_guardian)

    orchestrator = PolyFactoryOrchestrator(base_path=BASE_PATH, risk_guardian=risk_guardian)
    scheduler = AgentScheduler(base_path=BASE_PATH, risk_guardian=risk_guardian)

    nightly_ran_today = _last_nightly_date(orchestrator)

    while not _shutdown:
        loop_start = time.monotonic()

        # 1. Sync orchestrator price cache from the connector's state file so that
        #    filter 0 (data_quality) always has current prices regardless of which
        #    consumer acked the feed:price_update bus events.
        _sync_price_cache(orchestrator)

        # 2. Orchestrator: consume bus events (trade:signals, risk, resolutions)
        try:
            actions = orchestrator.run_once()
            if actions:
                logger.debug("orchestrator processed %d action(s)", len(actions))
        except Exception:
            logger.exception("orchestrator.run_once failed — continuing.")

        # 3. Agent scheduler: feeds → C2 → strategies → execution → system
        try:
            scheduler.tick()
        except Exception:
            logger.exception("scheduler.tick failed — continuing.")

        # 4. Nightly cycle (once per UTC day at midnight)
        if _should_run_nightly(nightly_ran_today):
            now_utc = datetime.now(timezone.utc)
            if now_utc.hour == 0:
                try:
                    report = orchestrator.run_nightly()
                    nightly_ran_today = now_utc.strftime("%Y-%m-%d")
                    logger.info("Nightly cycle complete: %s", report)
                except Exception:
                    logger.exception("run_nightly failed.")

        # 5. Sleep for remainder of interval
        elapsed = time.monotonic() - loop_start
        sleep_s = max(0.0, POLL_INTERVAL_S - elapsed)
        if sleep_s > 0:
            time.sleep(sleep_s)

    logger.info("POLY_FACTORY orchestrator stopped.")


if __name__ == "__main__":
    main()
