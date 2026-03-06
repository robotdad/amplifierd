"""Context management routes for session conversation history."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from amplifierd.models.context import (
    AddMessageRequest,
    MessageItem,
    MessagesResponse,
    SetMessagesRequest,
)
from amplifierd.models.errors import ErrorTypeURI, ProblemDetail
from amplifierd.state.session_handle import SessionHandle

logger = logging.getLogger(__name__)

context_router = APIRouter(prefix="/sessions", tags=["context"])


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_handle_or_404(request: Request, session_id: str) -> SessionHandle:
    """Return SessionHandle or raise HTTPException 404 with RFC 7807 ProblemDetail body."""
    manager = request.app.state.session_manager
    handle = manager.get(session_id)
    if handle is None:
        detail = ProblemDetail(
            type=ErrorTypeURI.SESSION_NOT_FOUND,
            title="Session Not Found",
            status=404,
            detail=f"Session '{session_id}' not found",
            instance=str(request.url.path),
        )
        raise HTTPException(
            status_code=404,
            detail=detail.model_dump(exclude_none=True),
        )
    return handle


def _get_context(handle: SessionHandle) -> Any | None:
    """Return the context manager from the session, or None if not available."""
    return getattr(handle.session, "context", None)


def _context_unavailable_error(path: str) -> HTTPException:
    """Return a 503 HTTPException when context manager is not available."""
    detail = ProblemDetail(
        type=ErrorTypeURI.CONFIGURATION_ERROR,
        title="Context Manager Unavailable",
        status=503,
        detail="Context manager is not available for this session",
        instance=path,
    )
    return HTTPException(
        status_code=503,
        detail=detail.model_dump(exclude_none=True),
    )


def _build_messages_response(raw_messages: list[Any]) -> MessagesResponse:
    """Convert a list of raw message dicts/objects to MessagesResponse."""
    items: list[MessageItem] = []
    for msg in raw_messages:
        if isinstance(msg, dict):
            items.append(MessageItem(role=msg.get("role", ""), content=msg.get("content", "")))
        else:
            items.append(
                MessageItem(
                    role=getattr(msg, "role", ""),
                    content=getattr(msg, "content", ""),
                )
            )
    return MessagesResponse(messages=items, total=len(items))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@context_router.get("/{session_id}/context/messages", response_model=MessagesResponse)
async def get_messages(request: Request, session_id: str) -> MessagesResponse:
    """Get all conversation messages from a session's context."""
    handle = _get_handle_or_404(request, session_id)
    context = _get_context(handle)

    if context is None:
        return MessagesResponse(messages=[], total=0)

    try:
        raw = context.get_messages()
        return _build_messages_response(raw)
    except Exception:
        logger.warning(
            "Failed to get messages from context for session %s", session_id, exc_info=True
        )
        return MessagesResponse(messages=[], total=0)


@context_router.post(
    "/{session_id}/context/messages",
    status_code=201,
    response_model=MessageItem,
)
async def add_message(request: Request, session_id: str, body: AddMessageRequest) -> MessageItem:
    """Inject a single message into a session's context."""
    handle = _get_handle_or_404(request, session_id)
    context = _get_context(handle)

    if context is None:
        raise _context_unavailable_error(str(request.url.path))

    try:
        context.add_message(body.role, body.content)
    except Exception:
        logger.warning("Failed to add message to context for session %s", session_id, exc_info=True)
        raise _context_unavailable_error(str(request.url.path))

    return MessageItem(role=body.role, content=body.content)


@context_router.put("/{session_id}/context/messages", response_model=MessagesResponse)
async def set_messages(
    request: Request, session_id: str, body: SetMessagesRequest
) -> MessagesResponse:
    """Replace all context messages for a session."""
    handle = _get_handle_or_404(request, session_id)
    context = _get_context(handle)

    if context is None:
        raise _context_unavailable_error(str(request.url.path))

    raw_messages = [{"role": m.role, "content": m.content} for m in body.messages]
    try:
        context.set_messages(raw_messages)
    except Exception:
        logger.warning(
            "Failed to set messages on context for session %s", session_id, exc_info=True
        )
        raise _context_unavailable_error(str(request.url.path))

    try:
        updated = context.get_messages()
        return _build_messages_response(updated)
    except Exception:
        logger.warning(
            "Failed to read back messages after set for session %s", session_id, exc_info=True
        )
        return _build_messages_response(raw_messages)


@context_router.delete("/{session_id}/context/messages", status_code=204)
async def clear_messages(request: Request, session_id: str) -> None:
    """Clear all context messages for a session."""
    handle = _get_handle_or_404(request, session_id)
    context = _get_context(handle)

    if context is None:
        # Graceful no-op: clearing an absent context is not an error
        return

    try:
        context.clear()
    except Exception:
        logger.warning("Failed to clear context for session %s", session_id, exc_info=True)
