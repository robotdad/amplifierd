"""EventBus-backed display system for amplifierd.

Satisfies the display protocol expected by the coordinator.  Instead of
pushing to a queue (like the distro's QueueDisplaySystem), publishes
display_message events to the EventBus so all SSE subscribers receive them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from amplifierd.state.event_bus import EventBus

logger = logging.getLogger(__name__)


class EventBusDisplaySystem:
    """Display system that publishes messages to EventBus.

    Registered on the coordinator via ``coordinator.set("display", system)``.
    When hooks call ``coordinator.get("display").show_message()``, the
    message flows through EventBus to SSE subscribers.
    """

    def __init__(
        self,
        event_bus: EventBus,
        session_id: str,
        nesting_depth: int = 0,
    ) -> None:
        self._event_bus = event_bus
        self._session_id = session_id
        self._nesting_depth = nesting_depth

    async def show_message(
        self,
        message: str,
        level: Literal["info", "warning", "error"] = "info",
        source: str = "hook",
    ) -> None:
        """Publish a display message to the EventBus."""
        self._event_bus.publish(
            session_id=self._session_id,
            event_name="display_message",
            data={"message": message, "level": level, "source": source},
        )

    def push_nesting(self) -> EventBusDisplaySystem:
        """Return a new display system with incremented nesting depth."""
        return EventBusDisplaySystem(
            self._event_bus, self._session_id, self._nesting_depth + 1
        )

    def pop_nesting(self) -> EventBusDisplaySystem:
        """Return a new display system with decremented nesting depth."""
        return EventBusDisplaySystem(
            self._event_bus, self._session_id, max(0, self._nesting_depth - 1)
        )

    @property
    def nesting_depth(self) -> int:
        return self._nesting_depth
