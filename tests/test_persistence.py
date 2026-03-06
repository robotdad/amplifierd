"""Tests for session persistence hooks."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from amplifierd.persistence import (
    register_persistence_hooks,
    write_metadata,
    write_transcript,
)


def _msg(role: str, content: str | None = "text") -> dict[str, Any]:
    return {"role": role, "content": content}


@pytest.mark.unit
class TestWriteTranscript:
    """Tests for write_transcript()."""

    def test_creates_file(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "session-abc"
        write_transcript(session_dir, [_msg("user", "hello"), _msg("assistant", "hi")])
        transcript = session_dir / "transcript.jsonl"
        assert transcript.exists()
        lines = transcript.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["role"] == "user"
        assert json.loads(lines[1])["role"] == "assistant"

    def test_filters_system_roles(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "session-abc"
        write_transcript(
            session_dir,
            [
                _msg("system", "sys prompt"),
                _msg("developer", "dev note"),
                _msg("user", "hello"),
            ],
        )
        lines = (session_dir / "transcript.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["role"] == "user"

    def test_preserves_content_null(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "session-abc"
        write_transcript(session_dir, [_msg("assistant", None)])
        lines = (session_dir / "transcript.jsonl").read_text().strip().split("\n")
        parsed = json.loads(lines[0])
        assert parsed["content"] is None

    def test_empty_messages(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "session-abc"
        write_transcript(session_dir, [])
        content = (session_dir / "transcript.jsonl").read_text()
        assert content == ""

    def test_creates_dir_if_missing(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "nested" / "session"
        write_transcript(session_dir, [_msg("user", "hi")])
        assert session_dir.exists()
        assert (session_dir / "transcript.jsonl").exists()


@pytest.mark.unit
class TestWriteMetadata:
    """Tests for write_metadata()."""

    def test_creates_file(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "session-abc"
        session_dir.mkdir()
        write_metadata(session_dir, {"session_id": "abc", "turn_count": 1})
        meta = json.loads((session_dir / "metadata.json").read_text())
        assert meta["session_id"] == "abc"
        assert meta["turn_count"] == 1

    def test_merges_existing(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "session-abc"
        session_dir.mkdir()
        (session_dir / "metadata.json").write_text(
            json.dumps({"name": "My Session", "turn_count": 1})
        )
        write_metadata(session_dir, {"turn_count": 2, "last_updated": "2026-01-01"})
        meta = json.loads((session_dir / "metadata.json").read_text())
        assert meta["name"] == "My Session"  # preserved
        assert meta["turn_count"] == 2  # updated
        assert meta["last_updated"] == "2026-01-01"  # added

    def test_skips_missing_dir(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "nonexistent"
        write_metadata(session_dir, {"key": "val"})
        assert not (session_dir / "metadata.json").exists()

    def test_handles_corrupt_existing(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "session-abc"
        session_dir.mkdir()
        (session_dir / "metadata.json").write_text("{{not json")
        write_metadata(session_dir, {"key": "val"})
        meta = json.loads((session_dir / "metadata.json").read_text())
        assert meta["key"] == "val"


@pytest.mark.unit
class TestTranscriptSaveHook:
    """Tests for TranscriptSaveHook."""

    @pytest.mark.asyncio
    async def test_debounces(self, tmp_path: Path) -> None:
        from amplifierd.persistence import TranscriptSaveHook

        messages = [_msg("user", "hello")]
        context = MagicMock()
        context.get_messages = AsyncMock(return_value=messages)
        coordinator = MagicMock()
        coordinator.get = MagicMock(return_value=context)
        session = SimpleNamespace(coordinator=coordinator)

        session_dir = tmp_path / "session-abc"
        hook = TranscriptSaveHook(session, session_dir)

        # First call writes
        await hook("orchestrator:complete", {})
        assert (session_dir / "transcript.jsonl").exists()

        # Modify the file to detect if second call overwrites
        (session_dir / "transcript.jsonl").write_text("marker\n")

        # Second call with same count is no-op
        await hook("orchestrator:complete", {})
        assert (session_dir / "transcript.jsonl").read_text() == "marker\n"

    @pytest.mark.asyncio
    async def test_writes_on_new_messages(self, tmp_path: Path) -> None:
        from amplifierd.persistence import TranscriptSaveHook

        messages: list[dict[str, Any]] = [_msg("user", "hello")]
        context = MagicMock()
        context.get_messages = AsyncMock(return_value=messages)
        coordinator = MagicMock()
        coordinator.get = MagicMock(return_value=context)
        session = SimpleNamespace(coordinator=coordinator)

        session_dir = tmp_path / "session-abc"
        hook = TranscriptSaveHook(session, session_dir)

        await hook("orchestrator:complete", {})
        assert (session_dir / "transcript.jsonl").exists()

        # Add a message — should write again
        messages.append(_msg("assistant", "world"))
        context.get_messages = AsyncMock(return_value=messages)
        await hook("orchestrator:complete", {})
        lines = (session_dir / "transcript.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2


@pytest.mark.unit
class TestRegisterPersistenceHooks:
    """Tests for register_persistence_hooks()."""

    def test_noop_without_hooks_api(self) -> None:
        """No crash when coordinator lacks hooks."""
        session = SimpleNamespace(
            coordinator=SimpleNamespace(),  # no hooks attribute
            session_id="test",
        )
        # Should not raise
        register_persistence_hooks(session, Path("/tmp/test-session"))

    def test_registers_three_hooks(self) -> None:
        """Registers transcript (2 events) + metadata (1 event) = 3 hooks."""
        hooks = MagicMock()
        session = SimpleNamespace(
            coordinator=SimpleNamespace(hooks=hooks),
            session_id="test",
        )
        register_persistence_hooks(
            session, Path("/tmp/test-session"), {"session_id": "test"}
        )
        assert hooks.register.call_count == 3
        event_names = [call.kwargs["event"] for call in hooks.register.call_args_list]
        assert "tool:post" in event_names
        assert event_names.count("orchestrator:complete") == 2
