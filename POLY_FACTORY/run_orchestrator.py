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

from core.poly_factory_orchestrator import PolyFactoryOrchestrator

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


class AgentScheduler:
    """Calls each agent at its configured interval within the main loop.

    Agents run sequentially. Each agent's exception is caught independently
    so one failing agent never blocks the rest.

    Execution order per tick (dependency order):
      C1 feeds   → C2 signal agents → C3 strategies → execution chain → system
    """

    def __init__(self, base_path):
        # Each entry: (label, instance, interval_s, method_name)
        self._schedule = [
            # ── C1: Data feeds ──────────────────────────────────────────────
            # Connector fetches active markets + publishes feed:price_update
            ("connector",    ConnectorPolymarket(base_path=base_path),           300, "poll_markets"),
            # Binance REST snapshot → feed:binance_update + binance_raw.json
            ("binance_feed", PolyBinanceFeed(base_path=base_path),               30,  "poll_once"),
            # NOAA weather forecast → feed:noaa_update + noaa_forecasts.json
            ("noaa_feed",    PolyNoaaFeed(base_path=base_path),                  120, "poll_once"),
            # Polymarket wallet positions → feed:wallet_update
            ("wallet_feed",  PolyWalletFeed(base_path=base_path),                60,  "poll_once"),

            # ── C2: Signal processors ────────────────────────────────────────
            # Reads polymarket_prices.json → publishes signal:market_structure
            ("msa",          PolyMarketStructureAnalyzer(base_path=base_path),   30,  "run_once"),
            # Reads binance_raw.json → publishes signal:binance_score
            ("binance_sig",  PolyBinanceSignals(base_path=base_path),            10,  "run_once"),
            # Polls feed:wallet_update → publishes signal:wallet_convergence
            ("wallet_track", PolyWalletTracker(base_path=base_path),             60,  "run_once"),
            # Reads all feed state files → publishes data:validation_failed
            ("data_val",     PolyDataValidator(base_path=base_path),             10,  "run_once"),

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
            ("paper_engine", PolyPaperExecutionEngine(base_path=base_path),      2,   "run_once"),

            # ── System agents ────────────────────────────────────────────────
            ("heartbeat",    PolyHeartbeat(base_path=base_path),                 300, "run_once"),
            ("sys_monitor",  PolySystemMonitor(base_path=base_path),             300, "run_once"),
        ]
        self._last_run = {label: 0.0 for label, _, _, _ in self._schedule}

    def tick(self):
        """Run all agents whose interval has elapsed since their last call."""
        now = time.monotonic()
        for label, agent, interval, method in self._schedule:
            if now - self._last_run[label] >= interval:
                try:
                    getattr(agent, method)()
                except Exception:
                    logger.exception("Agent %s (%s) failed", label, method)
                self._last_run[label] = now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_run_nightly(last_nightly_date):
    """Return True if today's nightly cycle hasn't run yet."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return last_nightly_date != today


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

    orchestrator = PolyFactoryOrchestrator(base_path=BASE_PATH)
    scheduler = AgentScheduler(base_path=BASE_PATH)

    nightly_ran_today = _last_nightly_date(orchestrator)

    while not _shutdown:
        loop_start = time.monotonic()

        # 1. Orchestrator: consume bus events (trade:signals, risk, feed:price_update cache)
        #    Runs first so it captures fresh feed:price_update events before C2 agents
        #    overwrite them via state-file reads.
        try:
            actions = orchestrator.run_once()
            if actions:
                logger.debug("orchestrator processed %d action(s)", len(actions))
        except Exception:
            logger.exception("orchestrator.run_once failed — continuing.")

        # 2. Agent scheduler: feeds → C2 → strategies → execution → system
        try:
            scheduler.tick()
        except Exception:
            logger.exception("scheduler.tick failed — continuing.")

        # 3. Nightly cycle (once per UTC day at midnight)
        if _should_run_nightly(nightly_ran_today):
            now_utc = datetime.now(timezone.utc)
            if now_utc.hour == 0:
                try:
                    report = orchestrator.run_nightly()
                    nightly_ran_today = now_utc.strftime("%Y-%m-%d")
                    logger.info("Nightly cycle complete: %s", report)
                except Exception:
                    logger.exception("run_nightly failed.")

        # 4. Sleep for remainder of interval
        elapsed = time.monotonic() - loop_start
        sleep_s = max(0.0, POLL_INTERVAL_S - elapsed)
        if sleep_s > 0:
            time.sleep(sleep_s)

    logger.info("POLY_FACTORY orchestrator stopped.")


if __name__ == "__main__":
    main()
