"""Session request/response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""

    bundle_name: str | None = None
    bundle_uri: str | None = None
    session_id: str | None = None
    parent_id: str | None = None
    working_dir: str | None = None
    config_overrides: dict[str, Any] | None = None


class PatchSessionRequest(BaseModel):
    """Request to patch an existing session."""

    working_dir: str | None = None
    name: str | None = None


class ResumeSessionRequest(BaseModel):
    """Request to resume a session from a directory."""

    session_dir: str


class ExecuteRequest(BaseModel):
    """Request to execute a prompt in a session."""

    prompt: str
    metadata: dict[str, Any] | None = None
    images: list[str] | None = None  # Passthrough — not yet wired to execution


class CancelRequest(BaseModel):
    """Request to cancel a running execution."""

    immediate: bool | None = None


class ForkRequest(BaseModel):
    """Request to fork a session at a specific turn."""

    turn: int
    handle_orphaned_tools: str | None = None


class StaleRequest(BaseModel):
    """Request to mark sessions as stale. Empty/extensible."""


class SessionSummary(BaseModel):
    """Summary of a session."""

    session_id: str
    status: str
    bundle: str | None = None
    created_at: str | None = None
    last_activity: str | None = None
    total_messages: int | None = None
    tool_invocations: int | None = None
    parent_session_id: str | None = None
    stale: bool | None = None


class SessionDetail(SessionSummary):
    """Detailed session info, extends SessionSummary."""

    working_dir: str | None = None
    stats: dict[str, Any] | None = None
    mounted_modules: list[Any] | None = None
    capabilities: dict[str, Any] | None = None


class SessionListResponse(BaseModel):
    """Response listing sessions."""

    sessions: list[SessionSummary]
    total: int


class ExecuteResponse(BaseModel):
    """Response from a prompt execution."""

    response: str | None = None
    usage: dict[str, Any] | None = None
    tool_calls: list[Any] | None = None
    finish_reason: str | None = None


class ExecuteStreamAccepted(BaseModel):
    """Response when streaming execution is accepted."""

    correlation_id: str
    session_id: str
    status: Literal["accepted"] = "accepted"


class CancelResponse(BaseModel):
    """Response from a cancel request."""

    state: str
    running_tools: list[str] | None = None


class CancelStatusResponse(BaseModel):
    """Detailed cancel status response."""

    state: str
    is_cancelled: bool
    is_graceful: bool
    is_immediate: bool
    running_tools: list[str]


class SessionTreeNode(BaseModel):
    """Recursive tree node representing session hierarchy."""

    session_id: str
    agent: str | None = None
    status: str | None = None
    children: list[SessionTreeNode] = []


class StaleResponse(BaseModel):
    """Response from marking a session as stale."""

    session_id: str
    stale: bool


class ForkResponse(BaseModel):
    """Response from forking a session."""

    session_id: str
    parent_id: str
    forked_from_turn: int
    message_count: int


class SetModeRequest(BaseModel):
    """Request to set the active mode for a session."""

    mode_name: str | None = None
