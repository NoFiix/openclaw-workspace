"""
POLY_HEARTBEAT — Agent liveness monitor for POLY_FACTORY.

Answers "Is this agent alive?" for each registered agent.
Agents call ping() to signal liveness. run_once() detects stale agents,
attempts automatic restarts, and disables agents after MAX_RESTARTS failures.

Frequency: every 30 min (scheduled by caller).
The restart_fn is injectable so no real PM2/OS calls are made in tests.
"""

import logging
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus


logger = logging.getLogger("POLY_HEARTBEAT")

PRODUCER = "POLY_HEARTBEAT"
STATE_FILE = "orchestrator/heartbeat_state.json"
STALE_MULTIPLIER = 2   # elapsed > 2 × expected_freq_s → stale
MAX_RESTARTS = 10      # disable agent after this many restart attempts


class PolyHeartbeat:
    """Agent liveness monitor with automatic restart and disable logic."""

    def __init__(self, base_path="state", restart_fn=None):
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self.restart_fn = restart_fn  # callable(agent_name: str) -> bool, or None
        self._state = self._load_state()

    def _load_state(self) -> dict:
        state = self.store.read_json(STATE_FILE)
        if state is None:
            state = {"agents": {}}
        return state

    def _save_state(self):
        self.store.write_json(STATE_FILE, self._state)

    def _now_utc(self) -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    def register(self, agent_name: str, expected_freq_s: float = 60.0):
        """Register an agent for heartbeat monitoring.

        No-op if already registered (preserves existing restart_count and status).
        """
        if agent_name not in self._state["agents"]:
            self._state["agents"][agent_name] = {
                "last_seen": None,
                "expected_freq_s": expected_freq_s,
                "restart_count": 0,
                "status": "active",
            }
            self._save_state()

    def ping(self, agent_name: str):
        """Record that an agent is alive. Auto-registers if unknown.

        Publishes system:heartbeat on the bus.
        """
        if agent_name not in self._state["agents"]:
            self.register(agent_name)

        now = self._now_utc()
        agent = self._state["agents"][agent_name]
        agent["last_seen"] = now
        # Revive: a successful ping proves the agent is alive — reset to active
        # even if previously disabled (the underlying issue has resolved)
        if agent["status"] == "disabled":
            logger.info("Agent %s revived by successful ping (was disabled, restart_count=%d)",
                        agent_name, agent.get("restart_count", 0))
        agent["status"] = "active"
        agent["restart_count"] = 0
        self._save_state()

        self.bus.publish(
            topic="system:heartbeat",
            producer=agent_name,
            payload={"agent": agent_name, "timestamp": now},
            priority="normal",
        )

    def check_stale(self) -> list:
        """Return list of active agents that have gone stale.

        Returns:
            List of {"agent", "last_seen", "restart_count"} dicts.
        """
        now = datetime.now(timezone.utc)
        stale = []

        for name, data in self._state["agents"].items():
            if data.get("status") == "disabled":
                continue

            last_seen = data.get("last_seen")
            if last_seen is None:
                # Never pinged → immediately stale
                stale.append({
                    "agent": name,
                    "last_seen": None,
                    "restart_count": data.get("restart_count", 0),
                })
                continue

            last_seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            elapsed = (now - last_seen_dt).total_seconds()
            threshold = STALE_MULTIPLIER * data.get("expected_freq_s", 60.0)

            if elapsed > threshold:
                stale.append({
                    "agent": name,
                    "last_seen": last_seen,
                    "restart_count": data.get("restart_count", 0),
                })

        return stale

    def _attempt_restart(self, agent_name: str) -> bool:
        """Attempt to restart an agent via the injectable restart_fn.

        Returns True if restart_fn returned True, False otherwise (including if
        restart_fn is None or raises an exception).
        """
        if self.restart_fn is None:
            return False
        try:
            return bool(self.restart_fn(agent_name))
        except Exception:
            return False

    def run_once(self) -> dict:
        """Check all registered agents, publish alerts, attempt restarts.

        Returns:
            Dict with checked_at, total_agents, stale_agents, restarted, disabled.
        """
        now = self._now_utc()
        stale = self.check_stale()
        restarted = []
        disabled = []

        for entry in stale:
            name = entry["agent"]
            agent = self._state["agents"][name]

            # Publish stale alert first (before incrementing count)
            self.bus.publish(
                topic="system:agent_stale",
                producer=PRODUCER,
                payload={
                    "agent": name,
                    "last_seen": entry["last_seen"],
                    "restart_count": agent["restart_count"],
                },
                priority="high",
            )

            # Increment restart counter
            agent["restart_count"] += 1

            if agent["restart_count"] <= MAX_RESTARTS:
                # Attempt restart
                success = self._attempt_restart(name)
                if success:
                    restarted.append(name)

            if agent["restart_count"] >= MAX_RESTARTS:
                # Disable after reaching the limit
                agent["status"] = "disabled"
                if name not in disabled:
                    disabled.append(name)
                self.bus.publish(
                    topic="system:agent_disabled",
                    producer=PRODUCER,
                    payload={"agent": name, "restart_count": agent["restart_count"]},
                    priority="high",
                )

        self._save_state()

        self.audit.log_event(
            topic="system:heartbeat",
            producer=PRODUCER,
            payload={
                "checked_at": now,
                "stale_count": len(stale),
                "restarted": restarted,
                "disabled": disabled,
            },
            priority="normal",
        )

        return {
            "checked_at": now,
            "total_agents": len(self._state["agents"]),
            "stale_agents": [e["agent"] for e in stale],
            "restarted": restarted,
            "disabled": disabled,
        }
