"""Tests for POLY_DATA_STORE — core/poly_data_store.py"""

import json
import os
import sqlite3

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.poly_data_store import PolyDataStore


@pytest.fixture
def store(tmp_path):
    """Create a PolyDataStore with a temporary base path."""
    return PolyDataStore(base_path=str(tmp_path))


class TestEnsureDirectories:
    def test_all_subdirs_created(self, store, tmp_path):
        for subdir in PolyDataStore.SUBDIRS:
            assert os.path.isdir(os.path.join(str(tmp_path), subdir))

    def test_idempotent(self, store):
        # Calling again should not raise
        store.ensure_directories()


class TestReadWriteJson:
    def test_roundtrip(self, store):
        data = {"key": "value", "nested": {"a": 1}, "list": [1, 2, 3]}
        store.write_json("test/file.json", data)
        result = store.read_json("test/file.json")
        assert result == data

    def test_read_missing_returns_none(self, store):
        assert store.read_json("nonexistent.json") is None

    def test_write_creates_parent_dirs(self, store, tmp_path):
        store.write_json("deep/nested/dir/file.json", {"ok": True})
        assert os.path.isfile(os.path.join(str(tmp_path), "deep/nested/dir/file.json"))

    def test_overwrite(self, store):
        store.write_json("file.json", {"v": 1})
        store.write_json("file.json", {"v": 2})
        assert store.read_json("file.json") == {"v": 2}

    def test_unicode(self, store):
        data = {"emoji": "\U0001f600", "accents": "caf\u00e9"}
        store.write_json("unicode.json", data)
        assert store.read_json("unicode.json") == data

    def test_atomic_no_temp_file_left(self, store, tmp_path):
        store.write_json("clean.json", {"ok": True})
        parent = os.path.join(str(tmp_path), ".")
        tmp_files = [f for f in os.listdir(str(tmp_path)) if f.endswith(".tmp")]
        assert len(tmp_files) == 0


class TestJsonl:
    def test_append_and_read(self, store):
        store.append_jsonl("log.jsonl", {"event": "a"})
        store.append_jsonl("log.jsonl", {"event": "b"})
        records = store.read_jsonl("log.jsonl")
        assert len(records) == 2
        assert records[0]["event"] == "a"
        assert records[1]["event"] == "b"

    def test_read_missing_returns_empty(self, store):
        assert store.read_jsonl("missing.jsonl") == []

    def test_1000_lines_integrity(self, store):
        rel = "stress.jsonl"
        for i in range(1000):
            store.append_jsonl(rel, {"index": i, "data": f"record_{i}"})

        records = store.read_jsonl(rel)
        assert len(records) == 1000

        for i, rec in enumerate(records):
            assert rec["index"] == i
            assert rec["data"] == f"record_{i}"

    def test_each_line_valid_json(self, store, tmp_path):
        rel = "valid.jsonl"
        for i in range(10):
            store.append_jsonl(rel, {"i": i})

        full_path = os.path.join(str(tmp_path), rel)
        with open(full_path, "r") as f:
            lines = f.readlines()

        assert len(lines) == 10
        for line in lines:
            assert line.endswith("\n")
            parsed = json.loads(line.strip())
            assert "i" in parsed


class TestArchive:
    def test_archive_moves_file(self, store, tmp_path):
        store.write_json("accounts/ACC_TEST.json", {"balance": 1000})
        dest = store.archive("accounts/ACC_TEST.json", "accounts/archive")

        assert not os.path.exists(os.path.join(str(tmp_path), "accounts/ACC_TEST.json"))
        assert os.path.exists(dest)

        with open(dest, "r") as f:
            data = json.load(f)
        assert data["balance"] == 1000

    def test_archive_missing_raises(self, store):
        with pytest.raises(FileNotFoundError):
            store.archive("nonexistent.json", "archive")

    def test_archive_filename_has_timestamp(self, store):
        store.write_json("test.json", {})
        dest = store.archive("test.json", "archive")
        basename = os.path.basename(dest)
        # Format: test_YYYYMMDD_HHMMSS.json
        assert basename.startswith("test_")
        assert basename.endswith(".json")
        assert len(basename) > len("test_.json")


class TestInitDefaultFiles:
    def test_all_json_files_created(self, store, tmp_path):
        store.init_default_files()
        for rel_path, expected in PolyDataStore.DEFAULT_FILES:
            full = os.path.join(str(tmp_path), rel_path)
            assert os.path.isfile(full), f"Missing: {rel_path}"
            with open(full, "r") as f:
                data = json.load(f)
            assert data == expected

    def test_all_jsonl_files_created(self, store, tmp_path):
        store.init_default_files()
        for rel_path in PolyDataStore.DEFAULT_JSONL_FILES:
            full = os.path.join(str(tmp_path), rel_path)
            assert os.path.isfile(full), f"Missing: {rel_path}"

    def test_idempotent(self, store):
        store.init_default_files()
        # Write something to a file
        store.write_json("feeds/polymarket_prices.json", {"price": 0.5})
        # Re-init should NOT overwrite existing files
        store.init_default_files()
        assert store.read_json("feeds/polymarket_prices.json") == {"price": 0.5}


class TestSqlite:
    def test_init_databases(self, store, tmp_path):
        store.init_databases()

        markets_db = os.path.join(str(tmp_path), "historical/markets.db")
        signals_db = os.path.join(str(tmp_path), "historical/signals.db")

        assert os.path.isfile(markets_db)
        assert os.path.isfile(signals_db)

        # Verify tables exist
        conn = sqlite3.connect(markets_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='markets'"
        )
        assert cursor.fetchone() is not None
        conn.close()

        conn = sqlite3.connect(signals_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='signals'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_init_sqlite_custom(self, store, tmp_path):
        store.init_sqlite("test.db", {
            "items": "CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, value TEXT)"
        })
        db_path = os.path.join(str(tmp_path), "test.db")
        assert os.path.isfile(db_path)

        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO items VALUES ('k1', 'v1')")
        conn.commit()
        row = conn.execute("SELECT * FROM items WHERE id='k1'").fetchone()
        assert row == ("k1", "v1")
        conn.close()

    def test_init_sqlite_idempotent(self, store):
        tables = {"t": "CREATE TABLE IF NOT EXISTS t (id TEXT)"}
        store.init_sqlite("idem.db", tables)
        store.init_sqlite("idem.db", tables)  # Should not raise


class TestExists:
    def test_exists_true(self, store):
        store.write_json("present.json", {})
        assert store.exists("present.json") is True

    def test_exists_false(self, store):
        assert store.exists("absent.json") is False
