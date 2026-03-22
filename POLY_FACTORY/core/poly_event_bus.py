"""
POLY_EVENT_BUS — File-based event bus for POLY_FACTORY.

Communication backbone: JSON Lines file + polling.
Supports publish/poll/ack cycle, idempotence, retry with dead letter,
priority ordering, and overwrite mode for feed topics.
Uses PolyDataStore for all file I/O.
"""

import collections
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from core.poly_data_store import PolyDataStore

logger = logging.getLogger("POLY_EVENT_BUS")

# Maps bus topic -> JSON schema filename (in schemas/ dir relative to this file's parent)
TOPIC_SCHEMAS = {
    "trade:signal":             "trade_signal.json",
    "execute:paper":            "execute_paper.json",
    "execute:live":             "execute_live.json",
    "feed:price_update":        "feed_price_update.json",
    "feed:noaa_update":         "feed_noaa_update.json",
    "feed:wallet_update":       "feed_wallet_update.json",
    "signal:binance_score":     "signal_binance_score.json",
    "signal:market_structure":  "signal_market_structure.json",
    "signal:wallet_convergence": "signal_wallet_convergence.json",
    "signal:resolution_parsed": "signal_resolution_parsed.json",
    "data:validation_failed":   "data_validation_failed.json",
    "system:health_check":      "system_health_report.json",
    "system:agent_stale":       "system_agent_stale.json",
    "system:agent_disabled":    "system_agent_disabled.json",
    "risk:kill_switch":         "risk_kill_switch_triggered.json",
    "risk:global_status":       "risk_global_halt.json",
    "trade:paper_executed":     "trade_paper_opened.json",
    "trade:paper_closed":       "trade_paper_closed.json",
    "trade:live_executed":      "trade_live_opened.json",
    "trade:live_closed":        "trade_live_closed.json",
}

_SCHEMAS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schemas")
_schema_cache = {}


def _load_schema(filename):
    """Load and cache a JSON schema from the schemas/ directory."""
    if filename in _schema_cache:
        return _schema_cache[filename]
    path = os.path.join(_SCHEMAS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    _schema_cache[filename] = schema
    return schema


def validate_payload(topic, payload):
    """Validate a payload dict against its JSON schema (draft-07).

    Non-blocking: logs a warning if the schema is absent.
    Returns False (invalid) if the payload fails validation so the caller
    can dead-letter the event. Returns True if valid or no schema exists.

    Args:
        topic:   Bus topic string.
        payload: Payload dict to validate.

    Returns:
        True if payload is valid (or no schema registered for this topic).
        False if payload is invalid per the schema.
    """
    schema_file = TOPIC_SCHEMAS.get(topic)
    if not schema_file:
        return True

    schema = _load_schema(schema_file)
    if schema is None:
        logger.warning("Schema file not found for topic %s: %s", topic, schema_file)
        return True

    try:
        import jsonschema  # noqa: PLC0415
        jsonschema.validate(instance=payload, schema=schema)
        return True
    except ImportError:
        # jsonschema not installed — skip validation, warn once
        logger.warning("jsonschema not installed; skipping payload validation for %s", topic)
        return True
    except jsonschema.ValidationError as e:
        logger.warning("Payload validation failed for topic %s: %s", topic, e.message)
        return False


# Topics that use overwrite mode: only the latest value per key matters.
# Maps topic -> payload field used as dedup key.
OVERWRITE_KEYS = {
    "feed:price_update": "market_id",
    "feed:binance_update": "symbol",
    "feed:noaa_update": "station",
    "feed:wallet_update": "wallet",
    "signal:binance_score": "symbol",
    "signal:market_structure": "market_id",
    "signal:wallet_convergence": "market_id",
}

MAX_RETRIES = 3
IDEMPOTENCE_SET_SIZE = 10_000

PENDING_FILE = "bus/pending_events.jsonl"
PROCESSED_FILE = "bus/processed_events.jsonl"
DEAD_LETTER_FILE = "bus/dead_letter.jsonl"


class PolyEventBus:
    """File-based event bus with polling, idempotence, and priority support."""

    # Class-level counter shared across all instances in the same process.
    # Prevents event_id collisions when multiple bus instances publish events
    # within the same second (e.g. orchestrator + arb_scanner in same loop tick).
    _class_counter: int = 0
    _class_counter_date: str | None = None
    _class_lock: threading.Lock = threading.Lock()

    # Class-level incremental file cache for pending_events.jsonl.
    # Shared across all instances in the same process to avoid re-parsing
    # the entire file (~48 MB, ~106 k lines) on every poll() call.
    # Invalidation: size < cached → compact detected → full re-read;
    #               size > cached → incremental read of new bytes only;
    #               size == cached → return cached list (zero I/O).
    _fc_lock: threading.Lock = threading.Lock()
    _fc_events: list = []
    _fc_size: int = 0
    _fc_path: str | None = None

    # Class-level acked IDs and consumer sets, shared across all instances.
    # Loaded once from processed_events.jsonl on first instantiation;
    # rebuilt during compact().  Prevents re-scanning the (potentially
    # multi-GB) processed file on every new PolyEventBus() instance.
    _ack_lock: threading.Lock = threading.Lock()
    _acked_ids: set = set()
    _consumer_processed: dict = {}
    _acked_loaded: bool = False

    def __init__(self, base_path="state"):
        self.store = PolyDataStore(base_path=base_path)
        self._lock = threading.Lock()

        # Poll call counter — used to throttle auto-compaction checks
        self._poll_count = 0

        # Load previously acked event_ids (once per process)
        with PolyEventBus._ack_lock:
            if not PolyEventBus._acked_loaded:
                self._load_acked_ids()
                PolyEventBus._acked_loaded = True

    def _load_acked_ids(self):
        """Load acked event_ids from processed_events.jsonl on startup.

        Only loads IDs that are still present in pending_events.jsonl,
        so memory stays proportional to the pending event count (~200 k
        IDs ≈ 15 MB) regardless of how large processed_events.jsonl is
        (can reach GB after a re-ack storm).
        """
        # 1. Build the set of IDs still in pending (fast: ~190 k lines)
        pending_path = self.store._resolve(PENDING_FILE)
        pending_ids = set()
        if os.path.exists(pending_path):
            with open(pending_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            eid = json.loads(line).get("event_id")
                            if eid:
                                pending_ids.add(eid)
                        except (json.JSONDecodeError, AttributeError):
                            pass

        if not pending_ids:
            return

        # 2. Scan processed and keep only IDs that are in pending
        full_path = self.store._resolve(PROCESSED_FILE)
        if not os.path.exists(full_path):
            return
        loaded = set()
        with open(full_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        eid = json.loads(line).get("event_id")
                        if eid and eid in pending_ids:
                            loaded.add(eid)
                    except (json.JSONDecodeError, AttributeError):
                        pass
        PolyEventBus._acked_ids = loaded
        logger.info(
            "_load_acked_ids: %d pending IDs, %d acked IDs loaded (from processed)",
            len(pending_ids), len(loaded),
        )

    def _generate_event_id(self):
        """Generate a unique event ID: EVT_{YYYYMMDD}_{HHMMSS}_{counter:04d}.

        The counter is class-level (shared across all instances in the process)
        to prevent collisions when multiple bus instances publish events within
        the same second.
        """
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        time_str = now.strftime("%H%M%S")

        with PolyEventBus._class_lock:
            if PolyEventBus._class_counter_date != date_str:
                PolyEventBus._class_counter = 0
                PolyEventBus._class_counter_date = date_str
            PolyEventBus._class_counter += 1
            counter = PolyEventBus._class_counter

        return f"EVT_{date_str}_{time_str}_{counter:04d}"

    def publish(self, topic, producer, payload, priority="normal"):
        """Publish an event to the bus.

        Args:
            topic: Event topic (e.g. "trade:signal", "feed:price_update").
            producer: Name of the producing agent.
            payload: Dict with event-specific data.
            priority: "normal" or "high".

        Returns:
            The full envelope dict.
        """
        # Validate payload against schema (warn-only; never blocks publish)
        validate_payload(topic, payload)

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

        self.store.append_jsonl(PENDING_FILE, envelope)
        return envelope

    def _read_pending_cached(self):
        """Read pending_events.jsonl with incremental caching.

        Uses a class-level cache shared across all PolyEventBus instances in
        the same process.  Between compacts the file only grows (appends), so
        we seek to the last-known size and parse only the new bytes.

        Invalidation rules:
          - size == cached  → zero I/O, return cached list
          - size >  cached  → read delta bytes, append parsed events
          - size <  cached  → file was rewritten (compact) → full re-read
        """
        full_path = self.store._resolve(PENDING_FILE)

        with PolyEventBus._fc_lock:
            try:
                file_size = os.path.getsize(full_path)
            except FileNotFoundError:
                PolyEventBus._fc_events = []
                PolyEventBus._fc_size = 0
                return []

            cached_size = PolyEventBus._fc_size

            # No change — return cached list (zero I/O)
            if file_size == cached_size and PolyEventBus._fc_path == full_path:
                return PolyEventBus._fc_events

            # Compact detected (or first call / different path) — full re-read
            if file_size < cached_size or PolyEventBus._fc_path != full_path:
                PolyEventBus._fc_events = self.store.read_jsonl(PENDING_FILE)
                PolyEventBus._fc_size = file_size
                PolyEventBus._fc_path = full_path
                return PolyEventBus._fc_events

            # File grew (append only) — read only new bytes
            with open(full_path, "r", encoding="utf-8") as f:
                f.seek(cached_size)
                new_data = f.read()

            for line in new_data.split("\n"):
                line = line.strip()
                if line:
                    try:
                        PolyEventBus._fc_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

            PolyEventBus._fc_size = file_size
            return PolyEventBus._fc_events

    def poll(self, consumer_id, topics=None):
        """Poll for unprocessed events.

        Args:
            consumer_id: Unique identifier for the consumer.
            topics: Optional list of topics to filter by. None = all topics.

        Returns:
            List of envelope dicts, sorted by priority (high first) then timestamp.
        """
        all_events = self._read_pending_cached()

        # Auto-compact: check every 200 polls, trigger if file exceeds 5 000 events
        self._poll_count += 1
        if self._poll_count % 200 == 0 and len(all_events) > 5_000:
            self.compact()

        # Ensure consumer has an idempotence set
        if consumer_id not in PolyEventBus._consumer_processed:
            PolyEventBus._consumer_processed[consumer_id] = set()

        consumer_seen = PolyEventBus._consumer_processed[consumer_id]

        # Filter: per-consumer only.  _acked_ids is NOT used here — it is
        # reserved for compact() age-based pruning.  Using it in poll()
        # broke pub/sub: the first consumer to ack an event made it
        # invisible to all other consumers sharing the class-level set.
        filtered = []
        for evt in all_events:
            eid = evt.get("event_id")
            if eid in consumer_seen:
                continue
            if topics is not None and evt.get("topic") not in topics:
                continue
            filtered.append(evt)

        # Apply overwrite dedup: for overwrite topics, keep only the latest per key
        result = []
        overwrite_latest = {}  # (topic, key_value) -> event

        for evt in filtered:
            topic = evt.get("topic", "")
            if topic in OVERWRITE_KEYS:
                key_field = OVERWRITE_KEYS[topic]
                key_value = evt.get("payload", {}).get(key_field, "")
                overwrite_key = (topic, key_value)
                overwrite_latest[overwrite_key] = evt
            else:
                result.append(evt)

        # Add the latest overwrite events
        result.extend(overwrite_latest.values())

        # Sort: high priority first, then by timestamp
        def sort_key(evt):
            priority_order = 0 if evt.get("priority") == "high" else 1
            return (priority_order, evt.get("timestamp", ""))

        result.sort(key=sort_key)

        return result

    def ack(self, consumer_id, event_id):
        """Acknowledge that a consumer has processed an event.

        Args:
            consumer_id: The consumer that processed the event.
            event_id: The event_id to acknowledge.
        """
        # Add to consumer's idempotence set
        if consumer_id not in PolyEventBus._consumer_processed:
            PolyEventBus._consumer_processed[consumer_id] = set()
        PolyEventBus._consumer_processed[consumer_id].add(event_id)

        # Add to global acked set
        PolyEventBus._acked_ids.add(event_id)

        # Persist to processed_events.jsonl
        self.store.append_jsonl(PROCESSED_FILE, {
            "event_id": event_id,
            "consumer_id": consumer_id,
            "acked_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S."
            ) + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z",
        })

    def retry(self, event_id):
        """Retry a failed event by incrementing its retry_count.

        If retry_count reaches MAX_RETRIES, the event is moved to dead_letter.

        Args:
            event_id: The event_id to retry.

        Returns:
            The new envelope (re-published or dead-lettered), or None if not found.
        """
        # Find the event in pending
        all_events = self.store.read_jsonl(PENDING_FILE)
        original = None
        for evt in all_events:
            if evt.get("event_id") == event_id:
                original = evt
                break

        if original is None:
            return None

        # Mark original as acked (consumed, will be replaced)
        PolyEventBus._acked_ids.add(event_id)

        new_retry_count = original.get("retry_count", 0) + 1

        if new_retry_count >= MAX_RETRIES:
            # Move to dead letter
            dead_event = dict(original)
            dead_event["retry_count"] = new_retry_count
            dead_event["dead_lettered_at"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3] + "Z"
            self.store.append_jsonl(DEAD_LETTER_FILE, dead_event)
            return dead_event

        # Re-publish with incremented retry_count
        now = datetime.now(timezone.utc)
        new_event_id = self._generate_event_id()

        retried = {
            "event_id": new_event_id,
            "topic": original["topic"],
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
            "producer": original["producer"],
            "priority": original.get("priority", "normal"),
            "retry_count": new_retry_count,
            "payload": original.get("payload", {}),
        }

        self.store.append_jsonl(PENDING_FILE, retried)
        return retried

    def get_dead_letters(self):
        """Read all dead-lettered events.

        Returns:
            List of dead-lettered envelope dicts.
        """
        return self.store.read_jsonl(DEAD_LETTER_FILE)

    def compact(self, max_age_hours=1):
        """Rewrite pending_events.jsonl removing only expired events.

        Age-only compaction: events are kept for max_age_hours regardless of
        ack status.  This preserves pub/sub semantics — every consumer has
        max_age_hours to poll and ack an event before it expires.  Per-consumer
        idempotence in poll() prevents reprocessing of already-acked events.

        Also truncates processed_events.jsonl to the same retention window
        to prevent unbounded growth (Fix C).

        Why max_age_hours=1:
          - Slowest consumer interval is 900 s (market_analyst).
          - 1 h = 4× safety margin over the slowest consumer.
          - Keeps pending_events.jsonl at ~50 MB steady-state (~110 k events).
          - Keeps _fc_events cache at ~220 MB (vs 850 MB at 4 h).
          - Keeps _consumer_processed at ~90 MB (vs 370 MB at 4 h).

        Args:
            max_age_hours: Remove events older than this. Default 1h.
        """
        import tempfile

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=max_age_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

        # --- Compact pending_events.jsonl (age-only) ---
        all_events = self.store.read_jsonl(PENDING_FILE)
        remaining = []
        for evt in all_events:
            ts = evt.get("timestamp", "")
            if ts < cutoff_str:
                continue  # expired
            remaining.append(evt)

        n_removed = len(all_events) - len(remaining)
        logger.info(
            "compact pending: %d → %d events (removed %d expired, cutoff %s)",
            len(all_events), len(remaining), n_removed, cutoff_str,
        )

        full_path = self.store._resolve(PENDING_FILE)
        dir_path = os.path.dirname(full_path)

        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for evt in remaining:
                    f.write(json.dumps(evt, ensure_ascii=False) + "\n")
            os.replace(tmp_path, full_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        # --- Rebuild in-memory acked sets after compaction ---
        # Keep only IDs that are still in the remaining pending events.
        # This bounds memory to the retention window and prevents stale
        # IDs from accumulating forever.
        remaining_ids = {evt.get("event_id") for evt in remaining if evt.get("event_id")}
        old_acked_size = len(PolyEventBus._acked_ids)
        PolyEventBus._acked_ids = PolyEventBus._acked_ids & remaining_ids
        for cid in PolyEventBus._consumer_processed:
            PolyEventBus._consumer_processed[cid] = (
                PolyEventBus._consumer_processed[cid] & remaining_ids
            )
        logger.info(
            "compact acked_ids: %d → %d (pruned %d stale)",
            old_acked_size, len(PolyEventBus._acked_ids),
            old_acked_size - len(PolyEventBus._acked_ids),
        )

        # --- Truncate processed_events.jsonl (same retention window) ---
        # Streaming approach: read line-by-line and write kept records
        # directly to a temp file, never loading the full file into memory
        # (it can reach multiple GB after a re-ack storm).
        processed_path = self.store._resolve(PROCESSED_FILE)
        if os.path.exists(processed_path):
            n_total = 0
            n_kept = 0
            fd2, tmp_path2 = tempfile.mkstemp(
                dir=os.path.dirname(processed_path), suffix=".tmp",
            )
            try:
                with os.fdopen(fd2, "w", encoding="utf-8") as fout:
                    with open(processed_path, "r", encoding="utf-8") as fin:
                        for line in fin:
                            line = line.strip()
                            if not line:
                                continue
                            n_total += 1
                            try:
                                rec = json.loads(line)
                                if rec.get("acked_at", "") >= cutoff_str:
                                    fout.write(line + "\n")
                                    n_kept += 1
                            except json.JSONDecodeError:
                                pass
                n_removed = n_total - n_kept
                if n_removed > 0:
                    logger.info(
                        "compact processed: %d → %d records (removed %d older than %s)",
                        n_total, n_kept, n_removed, cutoff_str,
                    )
                    os.replace(tmp_path2, processed_path)
                else:
                    os.unlink(tmp_path2)
            except Exception:
                if os.path.exists(tmp_path2):
                    os.unlink(tmp_path2)
                raise
