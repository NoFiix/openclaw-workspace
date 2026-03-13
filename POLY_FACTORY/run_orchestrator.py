"""
POLY_FACTORY — Orchestrator entry point.

Usage:
    python run_orchestrator.py [--mode paper|live]

Runs the central orchestrator in a polling loop:
  - run_once() every POLL_INTERVAL_S seconds (bus polling)
  - run_nightly() once per day at midnight UTC
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
# Config
# ---------------------------------------------------------------------------

POLL_INTERVAL_S = 2.0   # bus polling cadence (1-5s per architecture spec)
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
# Helpers
# ---------------------------------------------------------------------------

def _should_run_nightly(last_nightly_date: str | None) -> bool:
    """Return True if today's nightly cycle hasn't run yet."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return last_nightly_date != today


def _last_nightly_date(orchestrator: PolyFactoryOrchestrator) -> str | None:
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

    nightly_ran_today = _last_nightly_date(orchestrator)

    while not _shutdown:
        loop_start = time.monotonic()

        # --- Main cycle ---
        try:
            actions = orchestrator.run_once()
            if actions:
                logger.debug("run_once processed %d action(s)", len(actions))
        except Exception:
            logger.exception("run_once failed — continuing.")

        # --- Nightly cycle (once per UTC day) ---
        if _should_run_nightly(nightly_ran_today):
            now_utc = datetime.now(timezone.utc)
            if now_utc.hour == 0:
                try:
                    report = orchestrator.run_nightly()
                    nightly_ran_today = now_utc.strftime("%Y-%m-%d")
                    logger.info("Nightly cycle complete: %s", report)
                except Exception:
                    logger.exception("run_nightly failed.")

        # --- Sleep for remainder of interval ---
        elapsed = time.monotonic() - loop_start
        sleep_s = max(0.0, POLL_INTERVAL_S - elapsed)
        if sleep_s > 0:
            time.sleep(sleep_s)

    logger.info("POLY_FACTORY orchestrator stopped.")


if __name__ == "__main__":
    main()
