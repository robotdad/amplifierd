"""Tests for SessionManager — the central session registry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from amplifierd.config import DaemonSettings
from amplifierd.state.event_bus import EventBus
from amplifierd.state.session_manager import SessionManager


class TestSessionManager:
    @pytest.fixture
    def bus(self) -> EventBus:
        return EventBus()

    @pytest.fixture
    def settings(self) -> DaemonSettings:
        return DaemonSettings()

    @pytest.fixture
    def manager(self, bus: EventBus, settings: DaemonSettings) -> SessionManager:
        return SessionManager(event_bus=bus, settings=settings)

    def test_initially_empty(self, manager: SessionManager) -> None:
        assert manager.list_sessions() == []

    def test_get_nonexistent(self, manager: SessionManager) -> None:
        assert manager.get("nonexistent") is None

    async def test_register_and_get(self, manager: SessionManager) -> None:
        """Register a pre-built SessionHandle and retrieve it."""
        mock_session = MagicMock()
        mock_session.session_id = "test-123"
        mock_session.parent_id = None

        handle = manager.register(
            session=mock_session,
            prepared_bundle=None,
            bundle_name="test-bundle",
        )
        assert handle.session_id == "test-123"
        assert manager.get("test-123") is handle

    async def test_destroy(self, manager: SessionManager) -> None:
        mock_session = MagicMock()
        mock_session.session_id = "to-destroy"
        mock_session.parent_id = None
        mock_session.cleanup = AsyncMock()

        manager.register(
            session=mock_session,
            prepared_bundle=None,
            bundle_name="test-bundle",
        )
        assert manager.get("to-destroy") is not None
        await manager.destroy("to-destroy")
        assert manager.get("to-destroy") is None

    async def test_list_sessions(self, manager: SessionManager) -> None:
        for i in range(3):
            mock = MagicMock()
            mock.session_id = f"session-{i}"
            mock.parent_id = None
            manager.register(session=mock, prepared_bundle=None, bundle_name="b")

        sessions = manager.list_sessions()
        assert len(sessions) == 3
        ids = {s["session_id"] for s in sessions}
        assert ids == {"session-0", "session-1", "session-2"}
