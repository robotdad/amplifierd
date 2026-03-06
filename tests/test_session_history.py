"""Tests for historical session listing via SessionIndex integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from amplifierd.config import DaemonSettings
from amplifierd.state.event_bus import EventBus
from amplifierd.state.session_manager import SessionManager


@pytest.fixture()
def session_manager_with_index(tmp_path):
    """Factory: returns a callable that creates a SessionManager with index support."""

    def _factory(sessions_dir: Path) -> SessionManager:
        settings = DaemonSettings()
        event_bus = EventBus()
        return SessionManager(
            event_bus=event_bus,
            settings=settings,
            sessions_dir=sessions_dir,
        )

    return _factory


def test_list_sessions_includes_historical(tmp_path, session_manager_with_index):
    """Historical sessions from index appear in list_sessions()."""
    # Pre-populate sessions_dir with a historical session (metadata.json only, no in-memory handle)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True)
    sid = "historical-abc"
    sdir = sessions_dir / sid
    sdir.mkdir()
    (sdir / "metadata.json").write_text(
        json.dumps(
            {
                "session_id": sid,
                "bundle": "old-bundle",
                "created_at": "2026-03-01T10:00:00Z",
            }
        )
    )

    manager = session_manager_with_index(sessions_dir)
    sessions = manager.list_sessions()

    sids = [s.session_id if hasattr(s, "session_id") else s["session_id"] for s in sessions]
    assert sid in sids


def test_list_sessions_active_takes_priority_over_historical(tmp_path, session_manager_with_index):
    """An active in-memory session is not duplicated by the index."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True)

    sid = "active-and-indexed"
    # Put it in the index
    from amplifierd.state.session_index import SessionIndex, SessionIndexEntry

    index = SessionIndex(sessions_dir / "index.json")
    index.add(
        SessionIndexEntry(
            session_id=sid,
            status="completed",
            bundle="some-bundle",
            created_at="2026-03-01T10:00:00Z",
            last_activity="2026-03-01T10:00:00Z",
        )
    )
    index.save()

    manager = session_manager_with_index(sessions_dir)

    # Register the same session as active
    mock_session = MagicMock()
    mock_session.session_id = sid
    mock_session.parent_id = None
    manager.register(session=mock_session, prepared_bundle=None, bundle_name="live-bundle")

    sessions = manager.list_sessions()
    sids = [s.session_id if hasattr(s, "session_id") else s["session_id"] for s in sessions]
    # Should appear only once
    assert sids.count(sid) == 1


def test_register_adds_entry_to_index(tmp_path, session_manager_with_index):
    """Registering a new session writes it into the SessionIndex."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True)

    manager = session_manager_with_index(sessions_dir)

    mock_session = MagicMock()
    mock_session.session_id = "new-session-xyz"
    mock_session.parent_id = None
    manager.register(session=mock_session, prepared_bundle=None, bundle_name="my-bundle")

    # Index should know about the new session
    assert manager._index is not None  # noqa: SLF001
    entry = manager._index.get("new-session-xyz")  # noqa: SLF001
    assert entry is not None
    assert entry.bundle == "my-bundle"


async def test_destroy_updates_index_status(tmp_path, session_manager_with_index):
    """Destroying a session updates its status in the index."""
    from unittest.mock import AsyncMock

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True)

    manager = session_manager_with_index(sessions_dir)

    mock_session = MagicMock()
    mock_session.session_id = "to-destroy-idx"
    mock_session.parent_id = None
    mock_session.cleanup = AsyncMock()

    manager.register(session=mock_session, prepared_bundle=None, bundle_name="b")
    await manager.destroy("to-destroy-idx")

    assert manager._index is not None  # noqa: SLF001
    entry = manager._index.get("to-destroy-idx")  # noqa: SLF001
    assert entry is not None
    assert entry.status == "completed"
