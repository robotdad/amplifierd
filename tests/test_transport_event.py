"""Tests for TransportEvent – lightweight __slots__-based event carrier."""

import pytest

from amplifierd.state.transport_event import TransportEvent


@pytest.mark.unit
class TestTransportEvent:
    """Verify TransportEvent slots, defaults, and serialisation."""

    def test_creation(self):
        """Field values are stored correctly via keyword-only constructor."""
        evt = TransportEvent(
            event_name="tool:pre",
            data={"key": "value"},
            session_id="abc-123",
            timestamp="2025-01-01T00:00:00Z",
            correlation_id="prompt_abc-123_1",
            sequence=42,
        )
        assert evt.event_name == "tool:pre"
        assert evt.data == {"key": "value"}
        assert evt.session_id == "abc-123"
        assert evt.timestamp == "2025-01-01T00:00:00Z"
        assert evt.correlation_id == "prompt_abc-123_1"
        assert evt.sequence == 42

    def test_uses_slots(self):
        """TransportEvent uses __slots__ and does NOT have __dict__."""
        evt = TransportEvent(
            event_name="tool:pre",
            data={},
            session_id="s1",
            timestamp="2025-01-01T00:00:00Z",
        )
        assert hasattr(TransportEvent, "__slots__")
        assert not hasattr(evt, "__dict__")

    def test_defaults(self):
        """correlation_id defaults to None, sequence defaults to 0."""
        evt = TransportEvent(
            event_name="hook:post",
            data={"a": 1},
            session_id="sess-999",
            timestamp="2025-06-15T12:00:00Z",
        )
        assert evt.correlation_id is None
        assert evt.sequence == 0

    def test_to_dict(self):
        """to_sse_dict() returns the correct dict shape."""
        evt = TransportEvent(
            event_name="tool:pre",
            data={"payload": True},
            session_id="s-1",
            timestamp="2025-01-01T00:00:00Z",
            correlation_id="prompt_s-1_3",
            sequence=7,
        )
        result = evt.to_sse_dict()
        assert result == {
            "event": "tool:pre",
            "data": {"payload": True},
            "session_id": "s-1",
            "timestamp": "2025-01-01T00:00:00Z",
            "correlation_id": "prompt_s-1_3",
            "sequence": 7,
        }
