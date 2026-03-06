"""Event models for SSE and event history."""

from typing import Any

from pydantic import BaseModel


class SSEEnvelope(BaseModel):
    """Server-Sent Event envelope."""

    event: str
    data: Any
    session_id: str | None = None
    timestamp: str | None = None
    correlation_id: str | None = None
    sequence: int | None = None


class EventHistoryResponse(BaseModel):
    """Response containing event history."""

    events: list[Any]
    total: int
    has_more: bool
