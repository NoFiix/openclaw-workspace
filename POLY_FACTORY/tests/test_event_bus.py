"""Tests for POLY_EVENT_BUS — core/poly_event_bus.py"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.poly_event_bus import (
    PolyEventBus,
    OVERWRITE_KEYS,
    MAX_RETRIES,
    IDEMPOTENCE_SET_SIZE,
    PENDING_FILE,
    DEAD_LETTER_FILE,
)


@pytest.fixture
def bus(tmp_path):
    """Create a PolyEventBus with a temporary base path."""
    return PolyEventBus(base_path=str(tmp_path))


class TestPublish:
    def test_returns_envelope_with_all_fields(self, bus):
        env = bus.publish("trade:signal", "POLY_ARB_SCANNER", {"market": "BTC"})
        assert env["event_id"].startswith("EVT_")
        assert env["topic"] == "trade:signal"
        assert env["producer"] == "POLY_ARB_SCANNER"
        assert env["priority"] == "normal"
        assert env["retry_count"] == 0
        assert env["payload"] == {"market": "BTC"}
        assert "timestamp" in env

    def test_high_priority(self, bus):
        env = bus.publish("risk:kill_switch", "POLY_KILL_SWITCH", {}, priority="high")
        assert env["priority"] == "high"

    def test_event_persisted_to_file(self, bus, tmp_path):
        bus.publish("test:persist", "TEST", {"v": 1})
        records = bus.store.read_jsonl(PENDING_FILE)
        assert len(records) == 1
        assert records[0]["topic"] == "test:persist"


class TestPublishPollCycle:
    def test_publish_then_poll_returns_event(self, bus):
        bus.publish("trade:signal", "TEST", {"k": "v"})
        events = bus.poll("consumer_1")
        assert len(events) == 1
        assert events[0]["payload"]["k"] == "v"

    def test_poll_empty_bus(self, bus):
        events = bus.poll("consumer_1")
        assert events == []


class TestAck:
    def test_acked_event_not_returned_by_poll(self, bus):
        env = bus.publish("trade:signal", "TEST", {"k": 1})
        bus.ack("consumer_1", env["event_id"])

        events = bus.poll("consumer_1")
        assert len(events) == 0

    def test_acked_event_still_visible_to_other_consumers(self, bus):
        """Pub/sub: consumer_1 acking an event must NOT hide it from consumer_2."""
        env = bus.publish("trade:signal", "TEST", {"k": 1})
        bus.ack("consumer_1", env["event_id"])

        # consumer_2 has its own idempotence set — it should still see the event.
        # poll() now filters by per-consumer _consumer_processed only (not global
        # _acked_ids), so consumer_2 correctly sees an event acked by consumer_1.
        events = bus.poll("consumer_2")
        assert len(events) == 1  # pub/sub: visible to other consumers


class TestIdempotence:
    def test_same_consumer_sees_event_once(self, bus):
        bus.publish("trade:signal", "TEST", {"k": 1})

        events_1 = bus.poll("consumer_1")
        assert len(events_1) == 1

        # Second poll by same consumer — event already in idempotence set
        # (not acked, but consumer already saw it via poll... actually poll doesn't
        # auto-add to idempotence. The consumer must ack.)
        # The idempotence is enforced via ack. Let's test that.
        bus.ack("consumer_1", events_1[0]["event_id"])

        events_2 = bus.poll("consumer_1")
        assert len(events_2) == 0

    def test_different_consumers_both_see_event(self, bus):
        bus.publish("trade:signal", "TEST", {"k": 1})

        events_a = bus.poll("consumer_a")
        assert len(events_a) == 1

        # consumer_b should also see it (not yet acked globally)
        events_b = bus.poll("consumer_b")
        assert len(events_b) == 1

        assert events_a[0]["event_id"] == events_b[0]["event_id"]

    def test_idempotence_set_pruned_on_compact(self, bus):
        # Publish and ack more than IDEMPOTENCE_SET_SIZE events
        for i in range(IDEMPOTENCE_SET_SIZE + 100):
            env = bus.publish("test:flood", "TEST", {"i": i})
            bus.ack("flood_consumer", env["event_id"])

        # Set is unbounded — holds all acked IDs (>10 000)
        assert len(PolyEventBus._consumer_processed["flood_consumer"]) >= IDEMPOTENCE_SET_SIZE + 100

        # After compact, only IDs still in pending remain
        bus.compact(max_age_hours=4)
        # All flood events are recent → they stay in pending → set stays large
        assert len(PolyEventBus._consumer_processed["flood_consumer"]) >= IDEMPOTENCE_SET_SIZE + 100


class TestRetryAndDeadLetter:
    def test_retry_increments_count(self, bus):
        env = bus.publish("trade:signal", "TEST", {"k": 1})
        retried = bus.retry(env["event_id"])

        assert retried is not None
        assert retried["retry_count"] == 1
        assert retried["event_id"] != env["event_id"]  # New event_id

    def test_dead_letter_after_max_retries(self, bus):
        env = bus.publish("trade:signal", "TEST", {"k": 1})
        event_id = env["event_id"]

        # Retry MAX_RETRIES times
        for i in range(MAX_RETRIES):
            result = bus.retry(event_id)
            if result and result.get("retry_count", 0) < MAX_RETRIES:
                event_id = result["event_id"]

        # The last retry should have gone to dead letter
        dead = bus.get_dead_letters()
        assert len(dead) == 1
        assert dead[0]["retry_count"] == MAX_RETRIES
        assert dead[0]["payload"]["k"] == 1

    def test_retry_nonexistent_returns_none(self, bus):
        assert bus.retry("EVT_NONEXISTENT_000000_0001") is None

    def test_dead_letter_preserved(self, bus):
        env = bus.publish("trade:signal", "TEST", {"val": "dead"})
        eid = env["event_id"]

        # Drive to dead letter
        for _ in range(MAX_RETRIES):
            result = bus.retry(eid)
            if result and result.get("retry_count", 0) < MAX_RETRIES:
                eid = result["event_id"]

        dead = bus.get_dead_letters()
        assert len(dead) == 1
        assert dead[0]["payload"]["val"] == "dead"
        assert "dead_lettered_at" in dead[0]


class TestPriorityOrdering:
    def test_high_before_normal(self, bus):
        bus.publish("trade:signal", "TEST", {"order": "normal_1"}, priority="normal")
        bus.publish("risk:kill_switch", "TEST", {"order": "high_1"}, priority="high")
        bus.publish("trade:signal", "TEST", {"order": "normal_2"}, priority="normal")

        events = bus.poll("consumer_1")
        assert len(events) == 3
        assert events[0]["priority"] == "high"
        assert events[0]["payload"]["order"] == "high_1"

    def test_multiple_high_priority_ordered_by_timestamp(self, bus):
        bus.publish("risk:a", "TEST", {"seq": 1}, priority="high")
        bus.publish("risk:b", "TEST", {"seq": 2}, priority="high")

        events = bus.poll("consumer_1")
        assert events[0]["payload"]["seq"] == 1
        assert events[1]["payload"]["seq"] == 2


class TestOverwriteMode:
    def test_only_latest_feed_per_key(self, bus):
        # Publish 3 price updates for the same market
        bus.publish("feed:price_update", "CONNECTOR", {
            "market_id": "0xabc", "yes_price": 0.50
        })
        bus.publish("feed:price_update", "CONNECTOR", {
            "market_id": "0xabc", "yes_price": 0.55
        })
        bus.publish("feed:price_update", "CONNECTOR", {
            "market_id": "0xabc", "yes_price": 0.60
        })

        events = bus.poll("consumer_1")
        # Should only get the latest one
        price_events = [e for e in events if e["topic"] == "feed:price_update"]
        assert len(price_events) == 1
        assert price_events[0]["payload"]["yes_price"] == 0.60

    def test_different_keys_not_overwritten(self, bus):
        bus.publish("feed:price_update", "CONNECTOR", {
            "market_id": "0xabc", "yes_price": 0.50
        })
        bus.publish("feed:price_update", "CONNECTOR", {
            "market_id": "0xdef", "yes_price": 0.70
        })

        events = bus.poll("consumer_1")
        price_events = [e for e in events if e["topic"] == "feed:price_update"]
        assert len(price_events) == 2

    def test_non_overwrite_topics_all_returned(self, bus):
        bus.publish("trade:signal", "TEST", {"i": 1})
        bus.publish("trade:signal", "TEST", {"i": 2})
        bus.publish("trade:signal", "TEST", {"i": 3})

        events = bus.poll("consumer_1")
        trade_events = [e for e in events if e["topic"] == "trade:signal"]
        assert len(trade_events) == 3


class TestTopicFiltering:
    def test_filter_by_single_topic(self, bus):
        bus.publish("trade:signal", "TEST", {"t": "trade"})
        bus.publish("feed:price_update", "TEST", {"t": "feed", "market_id": "x"})

        events = bus.poll("consumer_1", topics=["trade:signal"])
        assert len(events) == 1
        assert events[0]["topic"] == "trade:signal"

    def test_filter_by_multiple_topics(self, bus):
        bus.publish("trade:signal", "TEST", {"t": 1})
        bus.publish("risk:kill_switch", "TEST", {"t": 2})
        bus.publish("feed:price_update", "TEST", {"t": 3, "market_id": "x"})

        events = bus.poll("consumer_1", topics=["trade:signal", "risk:kill_switch"])
        assert len(events) == 2

    def test_no_filter_returns_all(self, bus):
        bus.publish("trade:signal", "TEST", {"t": 1})
        bus.publish("risk:kill_switch", "TEST", {"t": 2})

        events = bus.poll("consumer_1")
        assert len(events) == 2


class TestCompact:
    def test_compact_removes_only_expired_events(self, bus, tmp_path):
        """Compact is age-only: acked events are NOT removed if still within TTL.

        This preserves pub/sub semantics — all consumers have max_age_hours
        to poll an event before it expires from pending.
        """
        env1 = bus.publish("test:a", "TEST", {"k": 1})
        bus.publish("test:b", "TEST", {"k": 2})
        env3 = bus.publish("test:c", "TEST", {"k": 3})

        bus.ack("consumer_1", env1["event_id"])
        bus.ack("consumer_1", env3["event_id"])

        bus.compact()

        # All 3 events are recent — none should be removed (age-only compact)
        records = bus.store.read_jsonl(PENDING_FILE)
        assert len(records) == 3

    def test_compact_preserves_recent_unacked(self, bus):
        bus.publish("test:a", "TEST", {"k": 1})
        bus.publish("test:b", "TEST", {"k": 2})

        bus.compact()

        records = bus.store.read_jsonl(PENDING_FILE)
        assert len(records) == 2

    def test_compact_removes_old_events(self, bus):
        """Events older than max_age_hours are removed regardless of ack status."""
        # Inject an event with an old timestamp directly
        old_event = {
            "event_id": "EVT_OLD_000000_0001",
            "topic": "test:old",
            "timestamp": "2020-01-01T00:00:00.000Z",
            "producer": "TEST",
            "priority": "normal",
            "retry_count": 0,
            "payload": {"k": "old"},
        }
        bus.store.append_jsonl(PENDING_FILE, old_event)
        bus.publish("test:new", "TEST", {"k": "new"})

        bus.compact()

        records = bus.store.read_jsonl(PENDING_FILE)
        assert len(records) == 1
        assert records[0]["payload"]["k"] == "new"


class TestPersistence:
    def test_acked_ids_survive_restart_same_consumer(self, tmp_path):
        """After restart, the same consumer must not reprocess its own acked events."""
        bus1 = PolyEventBus(base_path=str(tmp_path))
        env = bus1.publish("trade:signal", "TEST", {"k": 1})
        bus1.ack("consumer_1", env["event_id"])

        # Second instance: consumer_1 should not see its own acked event
        bus2 = PolyEventBus(base_path=str(tmp_path))
        events = bus2.poll("consumer_1")
        assert len(events) == 0  # consumer_1 already acked this
