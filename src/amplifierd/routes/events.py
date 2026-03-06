"""Global SSE events endpoint for real-time event streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse

from amplifierd.state.event_bus import EventBus

events_router = APIRouter(tags=["events"])

_KEEPALIVE_INTERVAL: float = 15.0


async def _event_generator(
    event_bus: EventBus,
    session_id: str | None = None,
    filter_patterns: list[str] | None = None,
) -> AsyncGenerator[str]:
    """Yield SSE-formatted strings by subscribing to the EventBus.

    Each event is serialized via ``event.to_sse_dict()`` with
    ``json.dumps(ensure_ascii=False)``.  A keepalive comment is sent
    every ``_KEEPALIVE_INTERVAL`` seconds to prevent proxy timeouts.
    """
    async for event in event_bus.subscribe(
        session_id=session_id,
        filter_patterns=filter_patterns,
    ):
        sse_dict = event.to_sse_dict()
        name = sse_dict.get("event", event.event_name)
        data = json.dumps(sse_dict, ensure_ascii=False)
        yield f"event: {name}\ndata: {data}\n\n"


@events_router.get("/events")
async def stream_events(
    request: Request,
    session: str | None = None,
    filter: str | None = None,  # noqa: A002
    preset: str | None = None,
) -> StreamingResponse:
    """Stream real-time SSE events from the global EventBus."""
    event_bus: EventBus = request.app.state.event_bus

    filter_patterns: list[str] | None = None
    if filter:
        filter_patterns = [p.strip() for p in filter.split(",") if p.strip()]

    return StreamingResponse(
        _event_generator(
            event_bus=event_bus,
            session_id=session,
            filter_patterns=filter_patterns,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
