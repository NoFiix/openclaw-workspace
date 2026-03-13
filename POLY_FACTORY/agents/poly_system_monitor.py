"""
POLY_SYSTEM_MONITOR — Infrastructure health monitor for POLY_FACTORY.

Runs 4 surveillance layers: agents, APIs, infrastructure, and nightly coherence.
Issues are classified by severity: OK / WARNING / ALERT / CRITICAL.
All health input data is injectable (no real OS/PM2/network calls) for testability.

Monitoring intervals (caller's responsibility to schedule):
  - agents:     every 60s
  - APIs:       every 30s
  - infra:      every 5min
  - coherence:  nightly at 02:50 UTC
"""

import json
import os
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus


PRODUCER = "POLY_SYSTEM_MONITOR"
THRESHOLDS_FILE = "references/monitoring_thresholds.json"

LEVELS = {"OK", "WARNING", "ALERT", "CRITICAL"}

LEVEL_ORDER = {"OK": 0, "WARNING": 1, "ALERT": 2, "CRITICAL": 3}

_DEFAULT_THRESHOLDS = {
    "agents": {
        "max_memory_mb": 500,
        "max_cpu_pct": 90.0,
        "max_error_rate_per_min": 10,
        "stale_multiplier": 2,
    },
    "apis": {
        "latency_degraded_multiplier": 3,
    },
    "infra": {
        "min_disk_free_gb": 1.0,
        "max_ram_pct": 90.0,
        "max_cpu_5min_pct": 85.0,
    },
}


class PolySystemMonitor:
    """Infrastructure health monitor with 4 surveillance layers."""

    def __init__(self, base_path="state", thresholds=None):
        self.store = PolyDataStore(base_path=base_path)
        self.bus = PolyEventBus(base_path=base_path)
        self.audit = PolyAuditLog(base_path=base_path)
        self.thresholds = thresholds if thresholds is not None else self._load_thresholds()

    def _load_thresholds(self) -> dict:
        """Load thresholds from references/monitoring_thresholds.json.

        Falls back to hardcoded defaults on any error.
        """
        try:
            with open(THRESHOLDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return _DEFAULT_THRESHOLDS

    def _now_utc(self) -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    def _overall_level(self, issues: list) -> str:
        """Return the worst severity level across all issues. Empty list → 'OK'."""
        if not issues:
            return "OK"
        worst = 0
        for issue in issues:
            level = issue.get("level", "OK")
            worst = max(worst, LEVEL_ORDER.get(level, 0))
        for name, order in LEVEL_ORDER.items():
            if order == worst:
                return name
        return "OK"

    def check_agents(self, agent_statuses: list) -> list:
        """Check each agent for liveness, staleness, resource usage, and error rate.

        Args:
            agent_statuses: List of agent status dicts (see module docstring).

        Returns:
            List of {"agent", "issue", "level"} dicts.
        """
        issues = []
        cfg = self.thresholds.get("agents", _DEFAULT_THRESHOLDS["agents"])
        max_mem = cfg.get("max_memory_mb", 500)
        max_cpu = cfg.get("max_cpu_pct", 90.0)
        max_err = cfg.get("max_error_rate_per_min", 10)
        stale_mult = cfg.get("stale_multiplier", 2)

        for agent in agent_statuses:
            name = agent.get("name", "unknown")

            if not agent.get("alive", True):
                issues.append({"agent": name, "issue": "process not running", "level": "ALERT"})
                continue  # no point checking further metrics if process is down

            last_seen = agent.get("last_seen_seconds", 0)
            freq = agent.get("expected_freq_s", 60)
            if last_seen > stale_mult * freq:
                issues.append({"agent": name, "issue": "stale", "level": "WARNING"})

            if agent.get("memory_mb", 0) > max_mem:
                issues.append({"agent": name, "issue": "high memory", "level": "WARNING"})

            if agent.get("cpu_pct", 0) > max_cpu:
                issues.append({"agent": name, "issue": "high CPU", "level": "WARNING"})

            if agent.get("error_rate_per_min", 0) > max_err:
                issues.append({"agent": name, "issue": "high error rate", "level": "WARNING"})

        return issues

    def check_apis(self, api_statuses: list) -> list:
        """Check each external API for connectivity and latency.

        Args:
            api_statuses: List of API status dicts (see module docstring).

        Returns:
            List of {"api", "issue", "level"} dicts.
        """
        issues = []
        cfg = self.thresholds.get("apis", _DEFAULT_THRESHOLDS["apis"])
        degraded_mult = cfg.get("latency_degraded_multiplier", 3)

        for api in api_statuses:
            name = api.get("name", "unknown")

            if not api.get("connected", True):
                issues.append({"api": name, "issue": "api down", "level": "ALERT"})
                continue

            latency = api.get("latency_ms", 0)
            baseline = api.get("baseline_latency_ms", 0)
            if baseline > 0 and latency > degraded_mult * baseline:
                issues.append({"api": name, "issue": "latency degraded", "level": "WARNING"})

        return issues

    def check_infra(self, infra_status: dict) -> list:
        """Check infrastructure resources and database accessibility.

        Args:
            infra_status: Infra status dict (see module docstring).

        Returns:
            List of {"component", "issue", "level"} dicts.
        """
        issues = []
        cfg = self.thresholds.get("infra", _DEFAULT_THRESHOLDS["infra"])
        min_disk = cfg.get("min_disk_free_gb", 1.0)
        max_ram = cfg.get("max_ram_pct", 90.0)
        max_cpu_5min = cfg.get("max_cpu_5min_pct", 85.0)

        if infra_status.get("disk_free_gb", 999) < min_disk:
            issues.append({"component": "disk", "issue": "low disk space", "level": "ALERT"})

        if infra_status.get("ram_pct", 0) > max_ram:
            issues.append({"component": "ram", "issue": "high RAM usage", "level": "ALERT"})

        if infra_status.get("cpu_5min_pct", 0) > max_cpu_5min:
            issues.append({"component": "cpu", "issue": "high CPU average", "level": "WARNING"})

        if not infra_status.get("db_accessible", True):
            issues.append({"component": "database", "issue": "database inaccessible", "level": "ALERT"})

        return issues

    def check_coherence(self, accounts: dict, registry_entries: dict) -> list:
        """Check that account count matches active registry entries.

        Args:
            accounts: {account_id: account_data_dict}
            registry_entries: {strategy_name: registry_entry_dict}

        Returns:
            List of {"component", "issue", "level"} dicts.
        """
        issues = []

        if not accounts and not registry_entries:
            return issues

        active_count = sum(
            1 for entry in registry_entries.values()
            if entry.get("status", "stopped") != "stopped"
        )

        if len(accounts) != active_count:
            issues.append({
                "component": "registry",
                "issue": "account/registry count mismatch",
                "level": "ALERT",
            })

        return issues

    def run_once(
        self,
        agent_statuses=None,
        api_statuses=None,
        infra_status=None,
        accounts=None,
        registry_entries=None,
    ) -> dict:
        """Run all 4 health checks, publish bus events, and audit the run.

        Args:
            agent_statuses: List of agent status dicts. Defaults to [].
            api_statuses: List of API status dicts. Defaults to [].
            infra_status: Infra status dict. Defaults to {}.
            accounts: Accounts dict. Defaults to {}.
            registry_entries: Registry entries dict. Defaults to {}.

        Returns:
            Health summary dict with status, issues, and metadata.
        """
        now = self._now_utc()

        agent_issues = self.check_agents(agent_statuses or [])
        api_issues = self.check_apis(api_statuses or [])
        infra_issues = self.check_infra(infra_status or {})
        coherence_issues = self.check_coherence(accounts or {}, registry_entries or {})

        all_issues = agent_issues + api_issues + infra_issues + coherence_issues
        overall_status = self._overall_level(all_issues)

        # Always publish system:health_check
        self.bus.publish(
            topic="system:health_check",
            producer=PRODUCER,
            payload={
                "status": overall_status,
                "checked_at": now,
                "total_issues": len(all_issues),
                "agent_issues": len(agent_issues),
                "api_issues": len(api_issues),
                "infra_issues": len(infra_issues),
                "coherence_issues": len(coherence_issues),
            },
            priority="normal",
        )

        # Publish specific alerts if issues found
        if api_issues:
            self.bus.publish(
                topic="system:api_degraded",
                producer=PRODUCER,
                payload={"issues": api_issues, "checked_at": now},
                priority="high",
            )

        if infra_issues:
            self.bus.publish(
                topic="system:infra_warning",
                producer=PRODUCER,
                payload={"issues": infra_issues, "checked_at": now},
                priority="normal",
            )

        if coherence_issues:
            self.bus.publish(
                topic="system:coherence_error",
                producer=PRODUCER,
                payload={"issues": coherence_issues, "checked_at": now},
                priority="normal",
            )

        # Audit the run
        self.audit.log_event(
            topic="system:health_check",
            producer=PRODUCER,
            payload={
                "status": overall_status,
                "checked_at": now,
                "total_issues": len(all_issues),
            },
            priority="normal",
        )

        return {
            "status": overall_status,
            "checked_at": now,
            "agent_issues": agent_issues,
            "api_issues": api_issues,
            "infra_issues": infra_issues,
            "coherence_issues": coherence_issues,
            "total_issues": len(all_issues),
        }
