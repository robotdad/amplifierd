"""Tests for fork, turns, lineage, and forks endpoints on the sessions router."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from amplifierd.app import create_app
from amplifierd.config import DaemonSettings
from amplifierd.state.event_bus import EventBus
from amplifierd.state.session_handle import SessionHandle
from amplifierd.state.session_manager import SessionManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fake_cleanup() -> None:
    """No-op async cleanup."""


def _make_handle(
    session_id: str,
    *,
    event_bus: EventBus,
    parent_id: str | None = None,
    context: object | None = None,
) -> SessionHandle:
    """Create a minimal SessionHandle with a fake session."""
    fake_coordinator = SimpleNamespace(request_cancel=lambda immediate: None)
    fake_session = SimpleNamespace(
        session_id=session_id,
        parent_id=parent_id,
        coordinator=fake_coordinator,
        cleanup=_fake_cleanup,
        context=context,
    )
    return SessionHandle(
        session=fake_session,
        prepared_bundle=None,
        bundle_name="test-agent",
        event_bus=event_bus,
        working_dir=None,
    )


def _register_handle(
    client: TestClient,
    session_id: str,
    *,
    parent_id: str | None = None,
    context: object | None = None,
) -> SessionHandle:
    """Register a fake handle in the session manager and return it."""
    manager: SessionManager = client.app.state.session_manager  # type: ignore[union-attr]
    event_bus = manager._event_bus  # noqa: SLF001
    handle = _make_handle(session_id, event_bus=event_bus, parent_id=parent_id, context=context)
    manager._sessions[session_id] = handle  # noqa: SLF001
    return handle


def _make_messages(num_turns: int) -> list[dict]:
    """Build a simple conversation with num_turns user+assistant pairs."""
    msgs = []
    for i in range(1, num_turns + 1):
        msgs.append({"role": "user", "content": f"Question {i}"})
        msgs.append({"role": "assistant", "content": f"Answer {i}"})
    return msgs


@pytest.fixture()
def client() -> Generator[TestClient]:
    """Create a test client with session_manager on app.state."""
    app = create_app()
    settings = DaemonSettings()
    event_bus = EventBus()
    app.state.session_manager = SessionManager(event_bus=event_bus, settings=settings)
    app.state.background_tasks = set()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /sessions/{id}/fork
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestForkEndpoint:
    """Tests for POST /sessions/{session_id}/fork."""

    def test_fork_not_found_returns_404(self, client: TestClient) -> None:
        """POST /sessions/nonexistent/fork returns 404 with RFC 7807 ProblemDetail."""
        resp = client.post("/sessions/nonexistent/fork", json={"turn": 1})
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["type"] == "https://amplifier.dev/errors/session-not-found"
        assert detail["status"] == 404

    def test_fork_returns_fork_response_shape(self, client: TestClient) -> None:
        """POST /sessions/{id}/fork returns 200 with ForkResponse fields."""
        _register_handle(client, "sess-fork-1")
        resp = client.post("/sessions/sess-fork-1/fork", json={"turn": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "parent_id" in data
        assert "forked_from_turn" in data
        assert "message_count" in data

    def test_fork_parent_id_is_original_session(self, client: TestClient) -> None:
        """The parent_id in the response is the forked session's ID."""
        _register_handle(client, "sess-fork-2")
        resp = client.post("/sessions/sess-fork-2/fork", json={"turn": 1})
        assert resp.status_code == 200
        assert resp.json()["parent_id"] == "sess-fork-2"

    def test_fork_forked_from_turn_matches_request(self, client: TestClient) -> None:
        """forked_from_turn in response matches the requested turn."""
        messages = _make_messages(3)
        context = SimpleNamespace(get_messages=lambda: messages)
        _register_handle(client, "sess-fork-3", context=context)
        resp = client.post("/sessions/sess-fork-3/fork", json={"turn": 2})
        assert resp.status_code == 200
        assert resp.json()["forked_from_turn"] == 2

    def test_fork_with_messages_returns_message_count(self, client: TestClient) -> None:
        """When session has messages, fork returns correct message_count."""
        messages = _make_messages(2)  # 2 turns = 4 messages total
        context = SimpleNamespace(get_messages=lambda: messages)
        _register_handle(client, "sess-fork-4", context=context)
        resp = client.post("/sessions/sess-fork-4/fork", json={"turn": 1})
        assert resp.status_code == 200
        data = resp.json()
        # Turn 1: user + assistant = 2 messages
        assert data["message_count"] == 2

    def test_fork_new_session_id_differs_from_parent(self, client: TestClient) -> None:
        """The forked session_id is different from the original session_id."""
        _register_handle(client, "sess-fork-5")
        resp = client.post("/sessions/sess-fork-5/fork", json={"turn": 1})
        assert resp.status_code == 200
        assert resp.json()["session_id"] != "sess-fork-5"


# ---------------------------------------------------------------------------
# GET /sessions/{id}/fork/preview
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestForkPreviewEndpoint:
    """Tests for GET /sessions/{session_id}/fork/preview."""

    def test_preview_not_found_returns_404(self, client: TestClient) -> None:
        """GET /sessions/nonexistent/fork/preview returns 404."""
        resp = client.get("/sessions/nonexistent/fork/preview?turn=1")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["status"] == 404

    def test_preview_returns_turn_info(self, client: TestClient) -> None:
        """GET /sessions/{id}/fork/preview returns dict with 'turn' and 'message_count'."""
        _register_handle(client, "sess-prev-1")
        resp = client.get("/sessions/sess-prev-1/fork/preview?turn=1")
        assert resp.status_code == 200
        data = resp.json()
        assert "turn" in data
        assert "message_count" in data

    def test_preview_turn_matches_query_param(self, client: TestClient) -> None:
        """The 'turn' field in preview response matches the requested turn."""
        messages = _make_messages(3)
        context = SimpleNamespace(get_messages=lambda: messages)
        _register_handle(client, "sess-prev-2", context=context)
        resp = client.get("/sessions/sess-prev-2/fork/preview?turn=2")
        assert resp.status_code == 200
        assert resp.json()["turn"] == 2

    def test_preview_includes_max_turns(self, client: TestClient) -> None:
        """Preview response includes total max_turns count."""
        messages = _make_messages(3)
        context = SimpleNamespace(get_messages=lambda: messages)
        _register_handle(client, "sess-prev-3", context=context)
        resp = client.get("/sessions/sess-prev-3/fork/preview?turn=1")
        assert resp.status_code == 200
        assert resp.json()["max_turns"] == 3


# ---------------------------------------------------------------------------
# GET /sessions/{id}/turns
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTurnsEndpoint:
    """Tests for GET /sessions/{session_id}/turns."""

    def test_turns_not_found_returns_404(self, client: TestClient) -> None:
        """GET /sessions/nonexistent/turns returns 404."""
        resp = client.get("/sessions/nonexistent/turns")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["status"] == 404

    def test_turns_returns_list_and_total(self, client: TestClient) -> None:
        """GET /sessions/{id}/turns returns dict with 'turns' list and 'total'."""
        _register_handle(client, "sess-turns-1")
        resp = client.get("/sessions/sess-turns-1/turns")
        assert resp.status_code == 200
        data = resp.json()
        assert "turns" in data
        assert "total" in data
        assert isinstance(data["turns"], list)

    def test_turns_count_matches_messages(self, client: TestClient) -> None:
        """'total' reflects actual turn count from context messages."""
        messages = _make_messages(3)
        context = SimpleNamespace(get_messages=lambda: messages)
        _register_handle(client, "sess-turns-2", context=context)
        resp = client.get("/sessions/sess-turns-2/turns")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["turns"]) == 3

    def test_turns_each_item_has_turn_number(self, client: TestClient) -> None:
        """Each item in the turns list contains a 'turn' number."""
        messages = _make_messages(2)
        context = SimpleNamespace(get_messages=lambda: messages)
        _register_handle(client, "sess-turns-3", context=context)
        resp = client.get("/sessions/sess-turns-3/turns")
        assert resp.status_code == 200
        turns = resp.json()["turns"]
        assert all("turn" in t for t in turns)
        assert turns[0]["turn"] == 1
        assert turns[1]["turn"] == 2

    def test_turns_fallback_uses_handle_turn_count(self, client: TestClient) -> None:
        """Without context, turns list is derived from handle.turn_count (possibly 0)."""
        handle = _register_handle(client, "sess-turns-4")
        # handle has no context, turn_count=0 initially
        resp = client.get("/sessions/sess-turns-4/turns")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == handle.turn_count
        assert len(data["turns"]) == handle.turn_count


# ---------------------------------------------------------------------------
# GET /sessions/{id}/lineage
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLineageEndpoint:
    """Tests for GET /sessions/{session_id}/lineage."""

    def test_lineage_not_found_returns_404(self, client: TestClient) -> None:
        """GET /sessions/nonexistent/lineage returns 404."""
        resp = client.get("/sessions/nonexistent/lineage")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["status"] == 404

    def test_lineage_returns_sessions_and_total(self, client: TestClient) -> None:
        """GET /sessions/{id}/lineage returns dict with 'sessions' list and 'total'."""
        _register_handle(client, "sess-lin-1")
        resp = client.get("/sessions/sess-lin-1/lineage")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert "total" in data

    def test_lineage_includes_self_when_no_parent(self, client: TestClient) -> None:
        """A root session's lineage contains only itself (no parent)."""
        _register_handle(client, "sess-lin-2")
        resp = client.get("/sessions/sess-lin-2/lineage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["sessions"][0]["session_id"] == "sess-lin-2"

    def test_lineage_traverses_parent_chain(self, client: TestClient) -> None:
        """Lineage walks parent_id chain and returns sessions from root to current."""
        _register_handle(client, "sess-root")
        _register_handle(client, "sess-child", parent_id="sess-root")
        resp = client.get("/sessions/sess-child/lineage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        session_ids = [s["session_id"] for s in data["sessions"]]
        # Root comes first, child comes last
        assert session_ids[0] == "sess-root"
        assert session_ids[-1] == "sess-child"

    def test_lineage_stops_at_unknown_parent(self, client: TestClient) -> None:
        """If parent session is not in manager, lineage starts from the known session."""
        # sess-orphan has a parent that is not registered
        _register_handle(client, "sess-orphan", parent_id="unknown-parent")
        resp = client.get("/sessions/sess-orphan/lineage")
        assert resp.status_code == 200
        data = resp.json()
        # Only sess-orphan is known; unknown-parent is not included
        assert data["total"] == 1
        assert data["sessions"][0]["session_id"] == "sess-orphan"


# ---------------------------------------------------------------------------
# GET /sessions/{id}/forks
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestForksEndpoint:
    """Tests for GET /sessions/{session_id}/forks."""

    def test_forks_not_found_returns_404(self, client: TestClient) -> None:
        """GET /sessions/nonexistent/forks returns 404."""
        resp = client.get("/sessions/nonexistent/forks")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["status"] == 404

    def test_forks_returns_sessions_and_total(self, client: TestClient) -> None:
        """GET /sessions/{id}/forks returns dict with 'sessions' list and 'total'."""
        _register_handle(client, "sess-forks-1")
        resp = client.get("/sessions/sess-forks-1/forks")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert "total" in data

    def test_forks_empty_when_no_children(self, client: TestClient) -> None:
        """A session with no child forks returns empty list."""
        _register_handle(client, "sess-forks-2")
        resp = client.get("/sessions/sess-forks-2/forks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["sessions"] == []

    def test_forks_returns_sessions_with_this_parent(self, client: TestClient) -> None:
        """Returns sessions whose parent_id matches the requested session."""
        _register_handle(client, "sess-parent")
        _register_handle(client, "sess-fork-a", parent_id="sess-parent")
        _register_handle(client, "sess-fork-b", parent_id="sess-parent")
        _register_handle(client, "sess-other")  # unrelated
        resp = client.get("/sessions/sess-parent/forks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        fork_ids = {s["session_id"] for s in data["sessions"]}
        assert fork_ids == {"sess-fork-a", "sess-fork-b"}

    def test_forks_does_not_include_unrelated_sessions(self, client: TestClient) -> None:
        """Sessions with different parent_id are not included in forks list."""
        _register_handle(client, "sess-p1")
        _register_handle(client, "sess-p2")
        _register_handle(client, "sess-child-of-p2", parent_id="sess-p2")
        resp = client.get("/sessions/sess-p1/forks")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
