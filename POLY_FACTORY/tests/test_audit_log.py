"""Tests for POLY_AUDIT_LOG — core/poly_audit_log.py"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.poly_audit_log import PolyAuditLog, VALID_CATEGORIES


@pytest.fixture
def audit(tmp_path):
    """Create a PolyAuditLog with a temporary base path."""
    return PolyAuditLog(base_path=str(tmp_path))


class TestLogEvent:
    def test_returns_envelope_with_all_fields(self, audit):
        envelope = audit.log_event(
            topic="trade:signal",
            producer="POLY_ARB_SCANNER",
            payload={"market": "BTC-YES"},
            priority="normal",
        )
        assert "event_id" in envelope
        assert envelope["topic"] == "trade:signal"
        assert envelope["producer"] == "POLY_ARB_SCANNER"
        assert envelope["priority"] == "normal"
        assert envelope["retry_count"] == 0
        assert envelope["payload"] == {"market": "BTC-YES"}
        assert "timestamp" in envelope
        assert envelope["event_id"].startswith("EVT_")

    def test_default_priority_is_normal(self, audit):
        envelope = audit.log_event("test:topic", "TEST", {})
        assert envelope["priority"] == "normal"

    def test_high_priority(self, audit):
        envelope = audit.log_event("risk:kill_switch", "POLY_KILL_SWITCH", {}, priority="high")
        assert envelope["priority"] == "high"

    def test_timestamp_format(self, audit):
        envelope = audit.log_event("test:topic", "TEST", {})
        ts = envelope["timestamp"]
        # Format: YYYY-MM-DDTHH:MM:SS.mmmZ
        assert ts.endswith("Z")
        assert "T" in ts


class TestEventIdUniqueness:
    def test_100_rapid_events_unique_ids(self, audit):
        event_ids = set()
        for i in range(100):
            envelope = audit.log_event("test:rapid", "TEST", {"i": i})
            event_ids.add(envelope["event_id"])
        assert len(event_ids) == 100

    def test_event_id_format(self, audit):
        envelope = audit.log_event("test:format", "TEST", {})
        eid = envelope["event_id"]
        parts = eid.split("_")
        assert parts[0] == "EVT"
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 6  # HHMMSS
        assert len(parts[3]) == 4  # counter


class TestAppendOnly:
    def test_file_only_grows(self, audit, tmp_path):
        audit.log_event("test:a", "TEST", {"v": 1})
        today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
        path = os.path.join(str(tmp_path), "audit", f"audit_{today}.jsonl")

        size_after_1 = os.path.getsize(path)

        audit.log_event("test:b", "TEST", {"v": 2})
        size_after_2 = os.path.getsize(path)

        audit.log_event("test:c", "TEST", {"v": 3})
        size_after_3 = os.path.getsize(path)

        assert size_after_2 > size_after_1
        assert size_after_3 > size_after_2

    def test_all_events_present(self, audit):
        for i in range(10):
            audit.log_event("test:seq", "TEST", {"i": i})

        events = audit.read_events()
        assert len(events) == 10
        for i, ev in enumerate(events):
            assert ev["payload"]["i"] == i


class TestDailyRotation:
    def test_new_file_on_date_change(self, audit, tmp_path):
        day1 = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)

        with patch("core.poly_audit_log.datetime") as mock_dt:
            mock_dt.now.return_value = day1
            mock_dt.strptime = datetime.strptime
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            audit.log_event("test:day1", "TEST", {"day": 1})

        with patch("core.poly_audit_log.datetime") as mock_dt:
            mock_dt.now.return_value = day2
            mock_dt.strptime = datetime.strptime
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            audit.log_event("test:day2", "TEST", {"day": 2})

        file_day1 = os.path.join(str(tmp_path), "audit", "audit_2026_03_10.jsonl")
        file_day2 = os.path.join(str(tmp_path), "audit", "audit_2026_03_11.jsonl")

        assert os.path.isfile(file_day1)
        assert os.path.isfile(file_day2)

    def test_counter_resets_on_new_day(self, audit):
        day1 = datetime(2026, 3, 10, 23, 59, 59, tzinfo=timezone.utc)
        day2 = datetime(2026, 3, 11, 0, 0, 1, tzinfo=timezone.utc)

        with patch("core.poly_audit_log.datetime") as mock_dt:
            mock_dt.now.return_value = day1
            mock_dt.strptime = datetime.strptime
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            audit.log_event("test:eod", "TEST", {})

        with patch("core.poly_audit_log.datetime") as mock_dt:
            mock_dt.now.return_value = day2
            mock_dt.strptime = datetime.strptime
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            env = audit.log_event("test:sod", "TEST", {})

        # Counter should have reset — new day's first event gets counter 1
        assert env["event_id"].endswith("_0001")


class TestArchiveOld:
    def test_archives_files_older_than_max_age(self, audit, tmp_path):
        audit_dir = os.path.join(str(tmp_path), "audit")

        # Create an "old" audit file (100 days ago)
        old_date = datetime.now(timezone.utc) - timedelta(days=100)
        old_name = f"audit_{old_date.strftime('%Y_%m_%d')}.jsonl"
        old_path = os.path.join(audit_dir, old_name)
        with open(old_path, "w") as f:
            f.write('{"test": true}\n')

        # Create a "recent" audit file (10 days ago)
        recent_date = datetime.now(timezone.utc) - timedelta(days=10)
        recent_name = f"audit_{recent_date.strftime('%Y_%m_%d')}.jsonl"
        recent_path = os.path.join(audit_dir, recent_name)
        with open(recent_path, "w") as f:
            f.write('{"test": true}\n')

        archived = audit.archive_old(max_age_days=90)

        assert len(archived) == 1
        assert not os.path.exists(old_path)
        assert os.path.exists(recent_path)

        archive_dir = os.path.join(audit_dir, "archive")
        assert len(os.listdir(archive_dir)) == 1

    def test_archive_empty_when_all_recent(self, audit):
        audit.log_event("test:recent", "TEST", {})
        archived = audit.archive_old(max_age_days=90)
        assert archived == []


class TestReadEvents:
    def test_read_today(self, audit):
        audit.log_event("test:read", "TEST", {"k": "v"})
        events = audit.read_events()
        assert len(events) == 1
        assert events[0]["payload"]["k"] == "v"

    def test_read_specific_date(self, audit, tmp_path):
        # Manually create a file for a specific date
        audit_dir = os.path.join(str(tmp_path), "audit")
        with open(os.path.join(audit_dir, "audit_2026_01_15.jsonl"), "w") as f:
            f.write('{"event_id":"EVT_20260115_120000_0001","topic":"test","timestamp":"2026-01-15T12:00:00.000Z","producer":"TEST","priority":"normal","retry_count":0,"payload":{}}\n')

        events = audit.read_events(date_str="2026_01_15")
        assert len(events) == 1
        assert events[0]["event_id"] == "EVT_20260115_120000_0001"

    def test_read_nonexistent_date_returns_empty(self, audit):
        events = audit.read_events(date_str="2020_01_01")
        assert events == []


class TestCategories:
    def test_all_categories_log_successfully(self, audit):
        for cat in VALID_CATEGORIES:
            topic = f"{cat.lower()}:test"
            envelope = audit.log_event(topic, "TEST", {"category": cat})
            assert envelope["topic"] == topic


class TestFileParsability:
    def test_100_writes_all_parsable(self, audit, tmp_path):
        for i in range(100):
            audit.log_event("test:parse", "TEST", {"i": i})

        today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
        path = os.path.join(str(tmp_path), "audit", f"audit_{today}.jsonl")

        with open(path, "r") as f:
            lines = f.readlines()

        assert len(lines) == 100
        for line in lines:
            parsed = json.loads(line.strip())
            assert "event_id" in parsed
            assert "payload" in parsed
