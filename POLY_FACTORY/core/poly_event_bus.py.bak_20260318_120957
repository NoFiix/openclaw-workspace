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
from datetime import datetime, timezone

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

    def __init__(self, base_path="state"):
        self.store = PolyDataStore(base_path=base_path)
        self._lock = threading.Lock()

        # Per-consumer idempotence sets (bounded deques)
        self._consumer_processed = {}

        # Poll call counter — used to throttle auto-compaction checks
        self._poll_count = 0

        # Global deque of acked event_ids, bounded to last 10 000 (spec: CLAUDE.md)
        self._acked_ids = collections.deque(maxlen=IDEMPOTENCE_SET_SIZE)

        # Load previously acked event_ids from processed_events.jsonl
        self._load_acked_ids()

    def _load_acked_ids(self):
        """Load acked event_ids from processed_events.jsonl on startup."""
        records = self.store.read_jsonl(PROCESSED_FILE)
        for rec in records:
            eid = rec.get("event_id")
            if eid:
                self._acked_ids.append(eid)

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

    def poll(self, consumer_id, topics=None):
        """Poll for unprocessed events.

        Args:
            consumer_id: Unique identifier for the consumer.
            topics: Optional list of topics to filter by. None = all topics.

        Returns:
            List of envelope dicts, sorted by priority (high first) then timestamp.
        """
        all_events = self.store.read_jsonl(PENDING_FILE)

        # Auto-compact: check every 25 polls, trigger if file exceeds 5 000 events
        self._poll_count += 1
        if self._poll_count % 25 == 0 and len(all_events) > 5_000:
            self.compact()

        # Ensure consumer has an idempotence set
        if consumer_id not in self._consumer_processed:
            self._consumer_processed[consumer_id] = collections.deque(
                maxlen=IDEMPOTENCE_SET_SIZE
            )

        consumer_set = self._consumer_processed[consumer_id]
        consumer_seen = set(consumer_set)

        # Filter: not globally acked, not already seen by this consumer
        filtered = []
        for evt in all_events:
            eid = evt.get("event_id")
            if eid in self._acked_ids:
                continue
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
        if consumer_id not in self._consumer_processed:
            self._consumer_processed[consumer_id] = collections.deque(
                maxlen=IDEMPOTENCE_SET_SIZE
            )
        self._consumer_processed[consumer_id].append(event_id)

        # Add to global acked set
        self._acked_ids.append(event_id)

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
        self._acked_ids.append(event_id)

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

    def compact(self, max_age_hours=24):
        """Rewrite pending_events.jsonl removing acked and expired events.

        Maintenance operation to prevent unbounded file growth.
        Reads ALL acked IDs from processed_events.jsonl on disk (not just the
        in-memory deque which is capped at 10k) to ensure full cleanup.
        Also removes events older than max_age_hours to prevent unbounded
        growth of unacked events (e.g. system:heartbeat, feed overwrites).

        Args:
            max_age_hours: Remove unacked events older than this. Default 24h.
        """
        # Build complete set of acked IDs from disk — the in-memory deque
        # is bounded to 10k and loses older entries, causing stale events
        # to accumulate indefinitely.
        all_processed = self.store.read_jsonl(PROCESSED_FILE)
        all_acked = set()
        for rec in all_processed:
            eid = rec.get("event_id")
            if eid:
                all_acked.add(eid)
        # Also include in-memory acked IDs (may include recently acked not yet on disk)
        all_acked.update(self._acked_ids)

        # Compute age cutoff
        cutoff = datetime.now(timezone.utc)
        from datetime import timedelta
        cutoff = cutoff - timedelta(hours=max_age_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

        all_events = self.store.read_jsonl(PENDING_FILE)
        remaining = []
        for evt in all_events:
            eid = evt.get("event_id")
            if eid in all_acked:
                continue  # already processed
            ts = evt.get("timestamp", "")
            if ts < cutoff_str:
                continue  # expired (older than max_age_hours)
            remaining.append(evt)

        logger.info("compact: %d → %d events (removed %d acked + %d expired)",
                     len(all_events), len(remaining),
                     len(all_events) - len(remaining),  # total removed
                     0)  # approximate

        # Atomic rewrite via write_json pattern (write tmp + rename)
        full_path = self.store._resolve(PENDING_FILE)
        dir_path = os.path.dirname(full_path)

        import tempfile
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
