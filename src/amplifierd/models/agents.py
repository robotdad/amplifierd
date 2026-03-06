"""Agent request/response models."""

from typing import Any

from pydantic import BaseModel


class SpawnRequest(BaseModel):
    """Request to spawn a sub-agent."""

    agent: str
    instruction: str
    context_depth: str | None = None
    context_scope: str | None = None
    context_turns: int | None = None
    provider_preferences: list[Any] | None = None
    model_role: str | None = None


class SpawnResumeRequest(BaseModel):
    """Request to resume a spawned agent."""

    instruction: str


class SpawnResponse(BaseModel):
    """Response from spawning an agent."""

    output: str | None = None
    session_id: str | None = None
    status: str | None = None
    turn_count: int | None = None
    metadata: dict[str, Any] | None = None


class AgentInfo(BaseModel):
    """Information about an available agent."""

    description: str | None = None
    model_role: str | None = None


class AgentListResponse(BaseModel):
    """Response listing available agents."""

    agents: dict[str, AgentInfo]
