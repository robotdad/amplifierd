"""Lightweight __slots__-based event carrier for the internal EventBus hot path."""

from __future__ import annotations

from typing import Any


class TransportEvent:
    """Minimal event envelope optimised for the SSE / EventBus hot path.

    Uses ``__slots__`` instead of Pydantic for memory efficiency and fast
    attribute access.
    """

    __slots__ = (
        "event_name",
        "data",
        "session_id",
        "timestamp",
        "correlation_id",
        "sequence",
    )

    def __init__(
        self,
        *,
        event_name: str,
        data: dict[str, Any],
        session_id: str,
        timestamp: str,
        correlation_id: str | None = None,
        sequence: int = 0,
    ) -> None:
        self.event_name = event_name
        self.data = data
        self.session_id = session_id
        self.timestamp = timestamp
        self.correlation_id = correlation_id
        self.sequence = sequence

    def to_sse_dict(self) -> dict[str, Any]:
        """Return a dict suitable for SSE serialisation."""
        return {
            "event": self.event_name,
            "data": self.data,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "sequence": self.sequence,
        }
