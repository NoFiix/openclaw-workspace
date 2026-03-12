"""
POLY_AUDIT_LOG — Immutable, append-only audit log for POLY_FACTORY.

Every significant event in the system is logged here as the single source of truth.
Daily-rotated JSONL files in state/audit/audit_YYYY_MM_DD.jsonl.
Uses PolyDataStore for file operations.
"""

import os
import threading
from datetime import datetime, timedelta, timezone

from core.poly_data_store import PolyDataStore


# Valid audit categories per implementation plan section 1.8
VALID_CATEGORIES = {
    "SIGNAL", "DECISION", "TRADE", "RISK", "HUMAN",
    "SYSTEM", "EVALUATION", "DATA", "ACCOUNT", "PROMOTION",
}


class PolyAuditLog:
    """Immutable, append-only audit log with daily rotation."""

    def __init__(self, base_path="state"):
        self.store = PolyDataStore(base_path=base_path)
        self.audit_dir = "audit"
        self.archive_dir = "audit/archive"
        self._counter = 0
        self._counter_date = None
        self._lock = threading.Lock()

    def _generate_event_id(self):
        """Generate a unique event ID: EVT_{YYYYMMDD}_{HHMMSS}_{counter:04d}.

        Thread-safe. Counter resets daily.
        """
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        time_str = now.strftime("%H%M%S")

        with self._lock:
            if self._counter_date != date_str:
                self._counter = 0
                self._counter_date = date_str
            self._counter += 1
            counter = self._counter

        return f"EVT_{date_str}_{time_str}_{counter:04d}"

    def _get_audit_file(self, date=None):
        """Return the relative path for a given date's audit file."""
        if date is None:
            date = datetime.now(timezone.utc)
        date_str = date.strftime("%Y_%m_%d")
        return f"{self.audit_dir}/audit_{date_str}.jsonl"

    def log_event(self, topic, producer, payload, priority="normal"):
        """Log an event to today's audit file.

        Args:
            topic: Event topic (e.g. "trade:signal", "risk:kill_switch").
            producer: Name of the producing agent (e.g. "POLY_ARB_SCANNER").
            payload: Dict with event-specific data.
            priority: "normal" or "high".

        Returns:
            The full envelope dict that was written.
        """
        now = datetime.now(timezone.utc)
        event_id = self._generate_event_id()

        envelope = {
            "event_id": event_id,
            "topic": topic,
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
            "producer": producer,
            "priority": priority,
            "retry_count": 0,
            "payload": payload,
        }

        audit_file = self._get_audit_file(now)
        self.store.append_jsonl(audit_file, envelope)

        return envelope

    def read_events(self, date_str=None):
        """Read all events from a specific day's audit file.

        Args:
            date_str: Date string in "YYYY_MM_DD" format. None = today.

        Returns:
            List of envelope dicts.
        """
        if date_str is None:
            audit_file = self._get_audit_file()
        else:
            audit_file = f"{self.audit_dir}/audit_{date_str}.jsonl"

        return self.store.read_jsonl(audit_file)

    def archive_old(self, max_age_days=90):
        """Move audit files older than max_age_days to the archive directory.

        Returns:
            List of archived file paths.
        """
        audit_full = self.store._resolve(self.audit_dir)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        archived = []

        for filename in os.listdir(audit_full):
            if not filename.startswith("audit_") or not filename.endswith(".jsonl"):
                continue

            # Parse date from filename: audit_YYYY_MM_DD.jsonl
            try:
                date_part = filename[6:-6]  # Remove "audit_" and ".jsonl"
                file_date = datetime.strptime(date_part, "%Y_%m_%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            if file_date < cutoff:
                rel_path = f"{self.audit_dir}/{filename}"
                dest = self.store.archive(rel_path, self.archive_dir)
                archived.append(dest)

        return archived
