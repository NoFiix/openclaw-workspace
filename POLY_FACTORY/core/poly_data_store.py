"""
POLY_DATA_STORE — Centralized persistence layer for POLY_FACTORY.

Single point of access for all persisted data (JSON files, JSONL logs, SQLite).
Uses only Python standard library. Atomic writes prevent corruption.
"""

import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone


class PolyDataStore:
    """Centralized persistence layer for all state/ files."""

    # All expected subdirectories under state/
    SUBDIRS = [
        "accounts",
        "accounts/archive",
        "audit",
        "audit/archive",
        "bus",
        "evaluation",
        "feeds",
        "historical",
        "human",
        "orchestrator",
        "registry",
        "research",
        "research/backtest_results",
        "risk",
        "trading",
        "trading/positions_by_strategy",
    ]

    # Default JSON files to initialize (relative to base_path)
    # Format: (rel_path, initial_content)
    DEFAULT_FILES = [
        ("feeds/polymarket_prices.json", {}),
        ("feeds/binance_raw.json", {}),
        ("feeds/binance_signals.json", {}),
        ("feeds/noaa_forecasts.json", {}),
        ("feeds/wallet_raw_positions.json", {}),
        ("feeds/wallet_signals.json", {}),
        ("feeds/market_structure.json", {}),
        ("evaluation/strategy_scores.json", {}),
        ("evaluation/strategy_rankings.json", {}),
        ("evaluation/tradability_reports.json", {}),
        ("evaluation/decay_alerts.json", {}),
        ("evaluation/tuning_recommendations.json", {}),
        ("risk/kill_switch_status.json", {}),
        ("risk/global_risk_state.json", {}),
        ("research/scouted_strategies.json", {}),
        ("research/resolutions_cache.json", {}),
        ("orchestrator/system_state.json", {}),
        ("orchestrator/strategy_lifecycle.json", {}),
        ("orchestrator/cycle_log.json", {}),
        ("registry/strategy_registry.json", {}),
        ("human/approvals.json", {}),
    ]

    # Default JSONL files (created empty)
    DEFAULT_JSONL_FILES = [
        "trading/paper_trades_log.jsonl",
        "trading/live_trades_log.jsonl",
        "bus/pending_events.jsonl",
        "bus/processed_events.jsonl",
        "bus/dead_letter.jsonl",
        "human/decisions_log.jsonl",
    ]

    def __init__(self, base_path="state"):
        self.base_path = os.path.abspath(base_path)
        self.ensure_directories()

    def _resolve(self, rel_path):
        """Resolve a relative path against the base_path."""
        return os.path.join(self.base_path, rel_path)

    def ensure_directories(self):
        """Create all expected state/ subdirectories."""
        for subdir in self.SUBDIRS:
            os.makedirs(self._resolve(subdir), exist_ok=True)

    def read_json(self, rel_path):
        """Read a JSON file. Returns None if file does not exist."""
        full_path = self._resolve(rel_path)
        if not os.path.exists(full_path):
            return None
        with open(full_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_json(self, rel_path, data):
        """Atomic write of data as JSON. Writes to temp file then renames."""
        full_path = self._resolve(rel_path)
        dir_path = os.path.dirname(full_path)
        os.makedirs(dir_path, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp_path, full_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def append_jsonl(self, rel_path, record):
        """Append a single JSON record as a line to a JSONL file."""
        full_path = self._resolve(rel_path)
        dir_path = os.path.dirname(full_path)
        os.makedirs(dir_path, exist_ok=True)

        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(line)

    def read_jsonl(self, rel_path):
        """Read all records from a JSONL file. Returns empty list if not found."""
        full_path = self._resolve(rel_path)
        if not os.path.exists(full_path):
            return []
        records = []
        with open(full_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def archive(self, rel_path, archive_dir):
        """Move a file to an archive directory with a timestamp suffix."""
        full_path = self._resolve(rel_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Cannot archive: {full_path} does not exist")

        archive_full = self._resolve(archive_dir)
        os.makedirs(archive_full, exist_ok=True)

        basename = os.path.basename(rel_path)
        name, ext = os.path.splitext(basename)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archived_name = f"{name}_{ts}{ext}"
        dest = os.path.join(archive_full, archived_name)

        shutil.move(full_path, dest)
        return dest

    def init_sqlite(self, rel_path, tables):
        """Initialize a SQLite database with the given table schemas.

        Args:
            rel_path: Path relative to base_path for the .db file.
            tables: Dict of {table_name: create_sql} where create_sql is
                    the full CREATE TABLE statement.
        """
        full_path = self._resolve(rel_path)
        dir_path = os.path.dirname(full_path)
        os.makedirs(dir_path, exist_ok=True)

        conn = sqlite3.connect(full_path)
        try:
            for table_name, create_sql in tables.items():
                conn.execute(create_sql)
            conn.commit()
        finally:
            conn.close()

    def init_default_files(self):
        """Create all default JSON and JSONL files if they don't exist."""
        for rel_path, content in self.DEFAULT_FILES:
            full_path = self._resolve(rel_path)
            if not os.path.exists(full_path):
                self.write_json(rel_path, content)

        for rel_path in self.DEFAULT_JSONL_FILES:
            full_path = self._resolve(rel_path)
            if not os.path.exists(full_path):
                with open(full_path, "w", encoding="utf-8") as f:
                    pass  # Create empty file

    def init_databases(self):
        """Initialize the historical SQLite databases."""
        self.init_sqlite("historical/markets.db", {
            "markets": (
                "CREATE TABLE IF NOT EXISTS markets ("
                "market_id TEXT PRIMARY KEY, "
                "data TEXT, "
                "updated_at TEXT)"
            ),
        })
        self.init_sqlite("historical/signals.db", {
            "signals": (
                "CREATE TABLE IF NOT EXISTS signals ("
                "signal_id TEXT PRIMARY KEY, "
                "data TEXT, "
                "created_at TEXT)"
            ),
        })

    def exists(self, rel_path):
        """Check if a file exists."""
        return os.path.exists(self._resolve(rel_path))
