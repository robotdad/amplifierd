"""Context management request/response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class MessageItem(BaseModel):
    """A single conversation message."""

    role: str
    content: Any  # str or structured content block list


class MessagesResponse(BaseModel):
    """Response containing a list of conversation messages."""

    messages: list[MessageItem]
    total: int


class AddMessageRequest(BaseModel):
    """Request body for injecting a single message into context."""

    role: str
    content: Any  # str or structured content block list


class SetMessagesRequest(BaseModel):
    """Request body for replacing all context messages."""

    messages: list[MessageItem]
