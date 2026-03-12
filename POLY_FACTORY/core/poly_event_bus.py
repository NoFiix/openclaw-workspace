"""
POLY_EVENT_BUS — File-based event bus for POLY_FACTORY.

Communication backbone: JSON Lines file + polling.
Supports publish/poll/ack cycle, idempotence, retry with dead letter,
priority ordering, and overwrite mode for feed topics.
Uses PolyDataStore for all file I/O.
"""

import collections
import json
import os
import threading
from datetime import datetime, timezone

from core.poly_data_store import PolyDataStore


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

    def __init__(self, base_path="state"):
        self.store = PolyDataStore(base_path=base_path)
        self._counter = 0
        self._counter_date = None
        self._lock = threading.Lock()

        # Per-consumer idempotence sets (bounded deques)
        self._consumer_processed = {}

        # Global set of acked event_ids (for filtering on poll)
        self._acked_ids = set()

        # Load previously acked event_ids from processed_events.jsonl
        self._load_acked_ids()

    def _load_acked_ids(self):
        """Load acked event_ids from processed_events.jsonl on startup."""
        records = self.store.read_jsonl(PROCESSED_FILE)
        for rec in records:
            eid = rec.get("event_id")
            if eid:
                self._acked_ids.add(eid)

    def _generate_event_id(self):
        """Generate a unique event ID: EVT_{YYYYMMDD}_{HHMMSS}_{counter:04d}."""
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
        self._acked_ids.add(event_id)

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
        self._acked_ids.add(event_id)

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

    def compact(self):
        """Rewrite pending_events.jsonl removing all acked events.

        Maintenance operation to prevent unbounded file growth.
        """
        all_events = self.store.read_jsonl(PENDING_FILE)
        remaining = [evt for evt in all_events if evt.get("event_id") not in self._acked_ids]

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
