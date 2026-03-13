"""
POLY-T03 — Tests bus et idempotence.

Covers exactly the 5 behaviors specified in the ticket:
  1. 1000 events → all present
  2. replay event_id → ignored
  3. 3 failures → dead_letter
  4. priority high → first
  5. overwrite mode
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.poly_event_bus import (
    PolyEventBus,
    MAX_RETRIES,
    OVERWRITE_KEYS,
    PENDING_FILE,
    DEAD_LETTER_FILE,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def bus(tmp_path):
    return PolyEventBus(base_path=str(tmp_path))


def _inject_raw(bus, envelope):
    """Append an envelope dict directly to PENDING_FILE, bypassing publish().

    Used to simulate event replay: the same event_id is re-inserted into the
    pending queue as if a producer erroneously re-sent it.
    """
    bus.store.append_jsonl(PENDING_FILE, envelope)


def _overwrite_payload(topic, key_value):
    """Build a minimal valid payload for an overwrite topic."""
    key_field = OVERWRITE_KEYS[topic]
    payload = {key_field: key_value}
    # Add required secondary fields for topics that need them
    if topic == "feed:price_update":
        payload.update({"yes_price": 0.50, "no_price": 0.50})
    elif topic == "feed:binance_update":
        payload.update({"price": 50000.0})
    elif topic == "feed:noaa_update":
        payload.update({"daily_max_forecast_f": 75.0})
    elif topic == "feed:wallet_update":
        payload.update({"positions": []})
    return payload


# ---------------------------------------------------------------------------
# 1. Bulk volume — 1000 events → all present
# ---------------------------------------------------------------------------

class TestBulkVolume:
    def test_1000_events_all_present(self, bus):
        """Publish 1000 non-overwrite events; poll must return all 1000."""
        for i in range(1000):
            bus.publish("trade:signal", "TEST", {"index": i})

        events = bus.poll("consumer_1")
        assert len(events) == 1000

    def test_1000_events_unique_ids(self, bus):
        """Every one of the 1000 events must have a distinct event_id."""
        published_ids = set()
        for i in range(1000):
            env = bus.publish("trade:signal", "TEST", {"i": i})
            published_ids.add(env["event_id"])

        assert len(published_ids) == 1000

        polled_ids = {e["event_id"] for e in bus.poll("consumer_1")}
        assert polled_ids == published_ids

    def test_1000_events_payload_integrity(self, bus):
        """Each polled event's payload must exactly match what was published."""
        for i in range(1000):
            bus.publish("trade:signal", "TEST", {"index": i, "data": f"v{i}"})

        events = bus.poll("consumer_1")
        # Sort by payload index to validate content regardless of ordering
        events.sort(key=lambda e: e["payload"]["index"])

        for i, evt in enumerate(events):
            assert evt["payload"]["index"] == i
            assert evt["payload"]["data"] == f"v{i}"


# ---------------------------------------------------------------------------
# 2. Idempotence replay — replay event_id → ignored
# ---------------------------------------------------------------------------

class TestIdempotenceReplay:
    def test_acked_event_not_returned_to_same_consumer(self, bus):
        """After ack, the same consumer must never see the event again."""
        env = bus.publish("trade:signal", "TEST", {"k": 1})
        bus.ack("consumer_1", env["event_id"])

        events = bus.poll("consumer_1")
        assert len(events) == 0

    def test_acked_event_not_returned_to_any_consumer(self, bus):
        """A globally acked event must be invisible to ALL consumers."""
        env = bus.publish("trade:signal", "TEST", {"k": 1})
        bus.ack("consumer_1", env["event_id"])

        for consumer_id in ("consumer_2", "consumer_3", "consumer_new"):
            events = bus.poll(consumer_id)
            assert len(events) == 0, f"{consumer_id} still saw acked event"

    def test_replay_acked_event_in_pending_ignored(self, bus):
        """Re-injecting an already-acked envelope into PENDING_FILE must be ignored."""
        env = bus.publish("trade:signal", "TEST", {"k": 1})
        bus.ack("consumer_1", env["event_id"])

        # Simulate a faulty producer replaying the exact same envelope
        _inject_raw(bus, env)

        events = bus.poll("consumer_1")
        assert len(events) == 0

    def test_replay_acked_event_ignored_by_all_consumers(self, bus):
        """Re-injected acked event must be invisible to any consumer."""
        env = bus.publish("trade:signal", "TEST", {"k": 99})
        bus.ack("consumer_1", env["event_id"])
        _inject_raw(bus, env)

        for consumer_id in ("consumer_1", "consumer_2", "consumer_fresh"):
            events = bus.poll(consumer_id)
            assert len(events) == 0, f"{consumer_id} saw replayed acked event"

    def test_replay_preserves_unacked_events(self, bus):
        """Re-injected acked event must not suppress unacked events in the queue."""
        acked_env = bus.publish("trade:signal", "TEST", {"role": "acked"})
        new_env = bus.publish("trade:signal", "TEST", {"role": "new"})

        bus.ack("consumer_1", acked_env["event_id"])

        # Re-inject the acked event
        _inject_raw(bus, acked_env)

        events = bus.poll("consumer_1")
        assert len(events) == 1
        assert events[0]["payload"]["role"] == "new"

    def test_acked_ids_persist_across_restart(self, tmp_path):
        """Acked event_ids must survive a PolyEventBus restart (loaded from file)."""
        bus1 = PolyEventBus(base_path=str(tmp_path))
        env = bus1.publish("trade:signal", "TEST", {"k": 1})
        bus1.ack("consumer_1", env["event_id"])

        # New instance: must reload acked_ids from processed_events.jsonl
        bus2 = PolyEventBus(base_path=str(tmp_path))
        events = bus2.poll("consumer_2")
        assert len(events) == 0


# ---------------------------------------------------------------------------
# 3. Dead letter — 3 failures → dead_letter
# ---------------------------------------------------------------------------

class TestDeadLetter:
    def _drive_to_dead_letter(self, bus):
        """Publish one event and retry until it reaches dead letter.

        Returns the final dead-letter record.
        """
        env = bus.publish("trade:signal", "TEST", {"val": "sentinel"})
        event_id = env["event_id"]

        result = None
        for _ in range(MAX_RETRIES):
            result = bus.retry(event_id)
            if result and result.get("retry_count", 0) < MAX_RETRIES:
                event_id = result["event_id"]

        return result

    def test_3_retries_land_in_dead_letter(self, bus):
        """Exactly MAX_RETRIES (3) retries must move the event to dead_letter."""
        self._drive_to_dead_letter(bus)

        dead = bus.get_dead_letters()
        assert len(dead) == 1

    def test_dead_letter_retry_count_equals_max(self, bus):
        """The dead-lettered event must have retry_count == MAX_RETRIES."""
        self._drive_to_dead_letter(bus)

        dead = bus.get_dead_letters()
        assert dead[0]["retry_count"] == MAX_RETRIES

    def test_dead_letter_payload_preserved(self, bus):
        """Original payload must be intact after dead-lettering."""
        self._drive_to_dead_letter(bus)

        dead = bus.get_dead_letters()
        assert dead[0]["payload"]["val"] == "sentinel"

    def test_dead_letter_has_dead_lettered_at_field(self, bus):
        """Dead-lettered event must include a 'dead_lettered_at' timestamp."""
        self._drive_to_dead_letter(bus)

        dead = bus.get_dead_letters()
        assert "dead_lettered_at" in dead[0]
        assert dead[0]["dead_lettered_at"].endswith("Z")

    def test_dead_letter_topic_preserved(self, bus):
        """Original topic must be preserved in the dead-letter record."""
        self._drive_to_dead_letter(bus)

        dead = bus.get_dead_letters()
        assert dead[0]["topic"] == "trade:signal"

    def test_partial_retry_not_yet_in_dead_letter(self, bus):
        """After only MAX_RETRIES-1 retries the event must NOT be in dead_letter."""
        env = bus.publish("trade:signal", "TEST", {"v": 1})
        event_id = env["event_id"]

        for _ in range(MAX_RETRIES - 1):
            result = bus.retry(event_id)
            if result and result.get("retry_count", 0) < MAX_RETRIES:
                event_id = result["event_id"]

        dead = bus.get_dead_letters()
        assert len(dead) == 0

    def test_dead_lettered_event_not_returned_by_poll(self, bus):
        """After dead-lettering, the event must not be visible via poll."""
        self._drive_to_dead_letter(bus)

        events = bus.poll("consumer_1", topics=["trade:signal"])
        assert len(events) == 0

    def test_multiple_events_dead_letter_independently(self, bus):
        """Two separate events can each be driven to dead_letter independently."""
        for label in ("alpha", "beta"):
            env = bus.publish("trade:signal", "TEST", {"label": label})
            eid = env["event_id"]
            for _ in range(MAX_RETRIES):
                result = bus.retry(eid)
                if result and result.get("retry_count", 0) < MAX_RETRIES:
                    eid = result["event_id"]

        dead = bus.get_dead_letters()
        assert len(dead) == 2
        labels = {d["payload"]["label"] for d in dead}
        assert labels == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# 4. Priority ordering — high priority → first
# ---------------------------------------------------------------------------

class TestPriorityOrdering:
    def test_high_priority_first(self, bus):
        """Single high-priority event published between two normals must appear first."""
        bus.publish("trade:signal", "TEST", {"order": 1}, priority="normal")
        bus.publish("risk:kill_switch", "TEST", {"order": 2}, priority="high")
        bus.publish("trade:signal", "TEST", {"order": 3}, priority="normal")

        events = bus.poll("consumer_1")
        assert len(events) == 3
        assert events[0]["priority"] == "high"
        assert events[0]["payload"]["order"] == 2

    def test_all_normals_after_high(self, bus):
        """All normal-priority events must appear after the high-priority one."""
        bus.publish("trade:signal", "TEST", {"seq": 1}, priority="normal")
        bus.publish("trade:signal", "TEST", {"seq": 2}, priority="normal")
        bus.publish("risk:a", "TEST", {"seq": 3}, priority="high")

        events = bus.poll("consumer_1")
        assert events[0]["priority"] == "high"
        for evt in events[1:]:
            assert evt["priority"] == "normal"

    def test_multiple_highs_in_timestamp_order(self, bus):
        """Multiple high-priority events must be sorted by timestamp ascending."""
        for seq in (1, 2, 3):
            bus.publish(f"risk:ev{seq}", "TEST", {"seq": seq}, priority="high")

        events = bus.poll("consumer_1")
        high_events = [e for e in events if e["priority"] == "high"]
        assert len(high_events) == 3
        seqs = [e["payload"]["seq"] for e in high_events]
        assert seqs == sorted(seqs)

    def test_normals_in_timestamp_order(self, bus):
        """Normal-priority events must be sorted by timestamp ascending."""
        for seq in (1, 2, 3):
            bus.publish("trade:signal", "TEST", {"seq": seq}, priority="normal")

        events = bus.poll("consumer_1")
        seqs = [e["payload"]["seq"] for e in events]
        assert seqs == sorted(seqs)

    def test_priority_respected_after_partial_ack(self, bus):
        """Priority ordering must hold even after some events have been acked."""
        n1 = bus.publish("trade:signal", "TEST", {"seq": 1}, priority="normal")
        bus.publish("trade:signal", "TEST", {"seq": 2}, priority="normal")
        bus.publish("risk:x", "TEST", {"seq": 3}, priority="high")

        bus.ack("consumer_1", n1["event_id"])

        events = bus.poll("consumer_1")
        assert len(events) == 2
        assert events[0]["priority"] == "high"


# ---------------------------------------------------------------------------
# 5. Overwrite mode — only latest per key survives
# ---------------------------------------------------------------------------

class TestOverwriteMode:
    def test_overwrite_keeps_only_latest_per_market(self, bus):
        """5 price_updates for the same market_id → poll returns exactly 1 (the latest)."""
        for price in (0.50, 0.55, 0.60, 0.65, 0.70):
            bus.publish("feed:price_update", "CONNECTOR", {
                "market_id": "0xabc",
                "yes_price": price,
                "no_price": 1 - price,
            })

        events = bus.poll("consumer_1")
        price_events = [e for e in events if e["topic"] == "feed:price_update"]
        assert len(price_events) == 1
        assert price_events[0]["payload"]["yes_price"] == pytest.approx(0.70)

    @pytest.mark.parametrize("topic,key_field", list(OVERWRITE_KEYS.items()))
    def test_all_overwrite_topics_dedup(self, bus, topic, key_field):
        """Every overwrite topic must deduplicate to 1 event per key value."""
        key_value = "test_key"
        for i in range(5):
            payload = _overwrite_payload(topic, key_value)
            payload["_seq"] = i  # marker to identify the latest
            bus.publish(topic, "TEST", payload)

        events = bus.poll("consumer_1")
        topic_events = [e for e in events if e["topic"] == topic]
        assert len(topic_events) == 1, (
            f"Expected 1 event for overwrite topic {topic!r}, got {len(topic_events)}"
        )
        # Must be the last published (_seq == 4)
        assert topic_events[0]["payload"]["_seq"] == 4

    def test_overwrite_different_keys_both_returned(self, bus):
        """Two different market_ids on the same overwrite topic must both be returned."""
        bus.publish("feed:price_update", "CONNECTOR", {
            "market_id": "0xaaa", "yes_price": 0.50, "no_price": 0.50,
        })
        bus.publish("feed:price_update", "CONNECTOR", {
            "market_id": "0xbbb", "yes_price": 0.60, "no_price": 0.40,
        })

        events = bus.poll("consumer_1")
        price_events = [e for e in events if e["topic"] == "feed:price_update"]
        assert len(price_events) == 2
        market_ids = {e["payload"]["market_id"] for e in price_events}
        assert market_ids == {"0xaaa", "0xbbb"}

    def test_non_overwrite_topic_all_retained(self, bus):
        """trade:signal is not an overwrite topic — all 10 events must be returned."""
        for i in range(10):
            bus.publish("trade:signal", "TEST", {"i": i})

        events = bus.poll("consumer_1")
        trade_events = [e for e in events if e["topic"] == "trade:signal"]
        assert len(trade_events) == 10

    def test_overwrite_mixed_with_normal_topics(self, bus):
        """Mix of overwrite and non-overwrite: overwrite deduped, normals all kept."""
        # 3 price updates for same market (overwrite) → should yield 1
        for price in (0.40, 0.50, 0.60):
            bus.publish("feed:price_update", "CONNECTOR", {
                "market_id": "0xccc", "yes_price": price, "no_price": 1 - price,
            })

        # 3 trade signals (non-overwrite) → should yield 3
        for i in range(3):
            bus.publish("trade:signal", "TEST", {"i": i})

        events = bus.poll("consumer_1")
        price_events = [e for e in events if e["topic"] == "feed:price_update"]
        trade_events = [e for e in events if e["topic"] == "trade:signal"]

        assert len(price_events) == 1
        assert price_events[0]["payload"]["yes_price"] == pytest.approx(0.60)
        assert len(trade_events) == 3

    def test_overwrite_latest_wins_after_many_updates(self, bus):
        """After 100 updates for the same key, only the 100th must survive."""
        for i in range(100):
            bus.publish("feed:binance_update", "BINANCE", {
                "symbol": "BTCUSDT",
                "price": 50000.0 + i,
                "seq": i,
            })

        events = bus.poll("consumer_1")
        binance_events = [e for e in events if e["topic"] == "feed:binance_update"]
        assert len(binance_events) == 1
        assert binance_events[0]["payload"]["seq"] == 99
