"""Tests for EventBus – global async event fanout with session-tree propagation."""

import asyncio

import pytest

from amplifierd.state.event_bus import EventBus
from amplifierd.state.transport_event import TransportEvent


@pytest.mark.unit
class TestEventBus:
    """Verify EventBus publish/subscribe, filtering, tree propagation, and tracking."""

    async def test_publish_and_subscribe(self):
        """Subscriber receives 2 published events in order."""
        bus = EventBus()
        received: list[TransportEvent] = []

        async def _consume():
            async for event in bus.subscribe():
                received.append(event)
                if len(received) == 2:
                    break

        task = asyncio.create_task(_consume())
        # Give the subscriber time to register
        await asyncio.sleep(0.05)

        bus.publish("s1", "evt.a", {"k": 1})
        bus.publish("s1", "evt.b", {"k": 2})

        await asyncio.wait_for(task, timeout=2.0)

        assert len(received) == 2
        assert received[0].event_name == "evt.a"
        assert received[0].data == {"k": 1}
        assert received[1].event_name == "evt.b"
        assert received[1].data == {"k": 2}
        # Sequence auto-increments per subscriber
        assert received[0].sequence == 1
        assert received[1].sequence == 2

    async def test_session_filter(self):
        """Subscriber with session_id only receives events for that session."""
        bus = EventBus()
        received: list[TransportEvent] = []

        async def _consume():
            async for event in bus.subscribe(session_id="s1"):
                received.append(event)
                if len(received) == 1:
                    break

        task = asyncio.create_task(_consume())
        await asyncio.sleep(0.05)

        # This should NOT be received (different session)
        bus.publish("s2", "evt.x", {"v": "no"})
        # This SHOULD be received (matching session)
        bus.publish("s1", "evt.y", {"v": "yes"})

        await asyncio.wait_for(task, timeout=2.0)

        assert len(received) == 1
        assert received[0].event_name == "evt.y"
        assert received[0].session_id == "s1"

    async def test_session_tree_propagation(self):
        """Parent subscriber receives events published to child sessions."""
        bus = EventBus()
        bus.register_child("parent", "child")

        received: list[TransportEvent] = []

        async def _consume():
            async for event in bus.subscribe(session_id="parent"):
                received.append(event)
                if len(received) == 1:
                    break

        task = asyncio.create_task(_consume())
        await asyncio.sleep(0.05)

        # Publish to child – parent subscriber should receive it
        bus.publish("child", "evt.from_child", {"origin": "child"})

        await asyncio.wait_for(task, timeout=2.0)

        assert len(received) == 1
        assert received[0].event_name == "evt.from_child"
        assert received[0].session_id == "child"

    async def test_subscriber_count(self):
        """subscriber_count tracks active subscribers."""
        bus = EventBus()
        assert bus.subscriber_count == 0

        received: list[TransportEvent] = []

        async def _consume():
            async for event in bus.subscribe():
                received.append(event)
                break

        task = asyncio.create_task(_consume())
        await asyncio.sleep(0.05)

        assert bus.subscriber_count == 1

        # Publish one event so the consumer breaks out
        bus.publish("s1", "evt.done", {})
        await asyncio.wait_for(task, timeout=2.0)

        # After consumer exits, subscriber should be cleaned up
        await asyncio.sleep(0.05)
        assert bus.subscriber_count == 0

    async def test_multi_subscriber_sequence_isolation(self):
        """Each subscriber gets independent sequence numbers on the same event."""
        bus = EventBus()
        received_a: list[TransportEvent] = []
        received_b: list[TransportEvent] = []

        async def _consume_a():
            async for event in bus.subscribe():
                received_a.append(event)
                if len(received_a) == 2:
                    break

        async def _consume_b():
            async for event in bus.subscribe():
                received_b.append(event)
                if len(received_b) == 2:
                    break

        task_a = asyncio.create_task(_consume_a())
        task_b = asyncio.create_task(_consume_b())
        await asyncio.sleep(0.05)

        bus.publish("s1", "evt.one", {"k": 1})
        bus.publish("s1", "evt.two", {"k": 2})

        await asyncio.wait_for(task_a, timeout=2.0)
        await asyncio.wait_for(task_b, timeout=2.0)

        # Both subscribers should have sequence 1, 2 independently
        assert received_a[0].sequence == 1
        assert received_a[1].sequence == 2
        assert received_b[0].sequence == 1
        assert received_b[1].sequence == 2
        # Events must be distinct objects (not shared references)
        assert received_a[0] is not received_b[0]
