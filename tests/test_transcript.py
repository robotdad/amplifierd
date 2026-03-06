"""Tests for GET /sessions/{id}/transcript — transcript loading endpoint."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from amplifierd.app import create_app
from amplifierd.state.session_manager import SessionManager


@pytest.fixture()
def sessions_dir(tmp_path: Path) -> Path:
    """Create a temporary sessions directory."""
    d = tmp_path / "sessions"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def client(sessions_dir: Path) -> Generator[TestClient]:
    """Test client with SessionManager configured with a sessions_dir.

    We patch sessions_dir onto the manager *after* lifespan runs (inside the
    context manager), so the lifespan's own SessionManager setup doesn't
    overwrite our value.  Same pattern as test_session_creation.py.
    """
    app = create_app()
    with TestClient(app) as c:
        manager: SessionManager = c.app.state.session_manager  # type: ignore[union-attr]
        manager._sessions_dir = sessions_dir  # noqa: SLF001
        yield c


def test_get_transcript_returns_messages(client: TestClient, sessions_dir: Path) -> None:
    """GET /sessions/{id}/transcript reads messages from transcript.jsonl."""
    sid = "test-session-123"
    sdir = sessions_dir / sid
    sdir.mkdir(parents=True)
    transcript = sdir / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "hello"})
        + "\n"
        + json.dumps({"role": "assistant", "content": "hi there"})
        + "\n"
    )

    resp = client.get(f"/sessions/{sid}/transcript")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "hello"
    assert data["messages"][1]["role"] == "assistant"
    assert data["session_id"] == sid
    # Frontend reads data.transcript; verify it matches data.messages
    assert data["transcript"] == data["messages"]
    assert isinstance(data["revision"], str)
    assert isinstance(data["last_updated"], str)


def test_get_transcript_missing_session(client: TestClient) -> None:
    """GET /sessions/{id}/transcript returns 404 when no transcript exists."""
    resp = client.get("/sessions/nonexistent/transcript")
    assert resp.status_code == 404


def test_get_transcript_skips_malformed_lines(client: TestClient, sessions_dir: Path) -> None:
    """GET /sessions/{id}/transcript skips lines that are not valid JSON."""
    sid = "session-malformed"
    sdir = sessions_dir / sid
    sdir.mkdir(parents=True)
    transcript = sdir / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "hello"})
        + "\n"
        + "NOT VALID JSON\n"
        + json.dumps({"role": "assistant", "content": "hi"})
        + "\n"
    )

    resp = client.get(f"/sessions/{sid}/transcript")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 2


def test_get_transcript_empty_file(client: TestClient, sessions_dir: Path) -> None:
    """GET /sessions/{id}/transcript returns empty messages for empty transcript."""
    sid = "session-empty"
    sdir = sessions_dir / sid
    sdir.mkdir(parents=True)
    (sdir / "transcript.jsonl").write_text("")

    resp = client.get(f"/sessions/{sid}/transcript")

    assert resp.status_code == 200
    data = resp.json()
    assert data["messages"] == []
