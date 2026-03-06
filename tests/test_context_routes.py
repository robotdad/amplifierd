"""Tests for context management routes (GET/POST/PUT/DELETE messages)."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amplifierd.app import create_app
from amplifierd.config import DaemonSettings
from amplifierd.state.event_bus import EventBus
from amplifierd.state.session_handle import SessionHandle
from amplifierd.state.session_manager import SessionManager

# -- Helpers --


async def _fake_cleanup() -> None:
    """No-op async cleanup for fake sessions."""


async def _fake_execute(prompt: str) -> str:
    """Stub execute that returns a predictable result."""
    return f"result:{prompt}"


def _make_handle(
    session_id: str,
    event_bus: EventBus,
    *,
    context: object | None = None,
) -> SessionHandle:
    """Create a minimal SessionHandle with a fake session and optional context."""
    fake_coordinator = SimpleNamespace(request_cancel=lambda immediate: None)
    fake_session = SimpleNamespace(
        session_id=session_id,
        parent_id=None,
        coordinator=fake_coordinator,
        cleanup=_fake_cleanup,
        execute=_fake_execute,
        context=context,
    )
    return SessionHandle(
        session=fake_session,
        prepared_bundle=None,
        bundle_name="test-bundle",
        event_bus=event_bus,
        working_dir=None,
    )


def _setup_app() -> FastAPI:
    """Create a test app with all required state."""
    app = create_app()
    settings = DaemonSettings()
    event_bus = EventBus()
    app.state.session_manager = SessionManager(event_bus=event_bus, settings=settings)
    app.state.background_tasks = set()
    app.state.event_bus = event_bus
    app.state.bundle_registry = None
    return app


def _register_session(
    app: FastAPI,
    session_id: str,
    *,
    context: object | None = None,
) -> SessionHandle:
    """Register a fake session in the session manager."""
    manager: SessionManager = app.state.session_manager
    event_bus = manager._event_bus  # noqa: SLF001
    handle = _make_handle(session_id, event_bus, context=context)
    manager._sessions[session_id] = handle  # noqa: SLF001
    return handle


# -- Fixtures --


@pytest.fixture()
def app() -> FastAPI:
    """Create a fresh test app."""
    return _setup_app()


@pytest.fixture()
def client(app: FastAPI) -> Generator[TestClient]:
    """Create a test client from the app."""
    with TestClient(app) as c:
        yield c


# -- GET /sessions/{id}/context/messages --


@pytest.mark.unit
class TestGetMessages:
    """Tests for GET /sessions/{id}/context/messages."""

    def test_session_not_found_returns_404(self, client: TestClient) -> None:
        """GET /sessions/nonexistent/context/messages returns 404."""
        resp = client.get("/sessions/nonexistent/context/messages")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/session-not-found"

    def test_returns_empty_when_no_context(self, client: TestClient, app: FastAPI) -> None:
        """GET returns empty messages when session has no context attribute."""
        _register_session(app, "sess-get-1", context=None)
        resp = client.get("/sessions/sess-get-1/context/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["messages"] == []
        assert data["total"] == 0

    def test_returns_messages_from_context(self, client: TestClient, app: FastAPI) -> None:
        """GET returns messages from the context manager."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        fake_context = SimpleNamespace(get_messages=lambda: messages)
        _register_session(app, "sess-get-2", context=fake_context)
        resp = client.get("/sessions/sess-get-2/context/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) == 2
        assert data["total"] == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "Hello"
        assert data["messages"][1]["role"] == "assistant"

    def test_tolerates_context_get_messages_failure(self, client: TestClient, app: FastAPI) -> None:
        """GET returns empty messages gracefully if get_messages() raises."""

        def _broken() -> None:
            raise RuntimeError("context broken")

        fake_context = SimpleNamespace(get_messages=_broken)
        _register_session(app, "sess-get-3", context=fake_context)
        resp = client.get("/sessions/sess-get-3/context/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["messages"] == []


# -- POST /sessions/{id}/context/messages --


@pytest.mark.unit
class TestAddMessage:
    """Tests for POST /sessions/{id}/context/messages."""

    def test_session_not_found_returns_404(self, client: TestClient) -> None:
        """POST /sessions/nonexistent/context/messages returns 404."""
        resp = client.post(
            "/sessions/nonexistent/context/messages",
            json={"role": "user", "content": "Hello"},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/session-not-found"

    def test_add_message_returns_201(self, client: TestClient, app: FastAPI) -> None:
        """POST returns 201 Created when message is injected."""
        added: list[dict[str, str]] = []
        fake_context = SimpleNamespace(
            add_message=lambda role, content: added.append({"role": role, "content": content}),
            get_messages=lambda: added,
        )
        _register_session(app, "sess-post-1", context=fake_context)
        resp = client.post(
            "/sessions/sess-post-1/context/messages",
            json={"role": "user", "content": "Hello"},
        )
        assert resp.status_code == 201

    def test_add_message_calls_context_add_message(self, client: TestClient, app: FastAPI) -> None:
        """POST calls context.add_message(role, content) with correct args."""
        captured: list[dict[str, str]] = []
        fake_context = SimpleNamespace(
            add_message=lambda role, content: captured.append({"role": role, "content": content}),
            get_messages=lambda: captured,
        )
        _register_session(app, "sess-post-2", context=fake_context)
        client.post(
            "/sessions/sess-post-2/context/messages",
            json={"role": "user", "content": "Test message"},
        )
        assert len(captured) == 1
        assert captured[0]["role"] == "user"
        assert captured[0]["content"] == "Test message"

    def test_add_message_response_contains_message(self, client: TestClient, app: FastAPI) -> None:
        """POST response body contains the injected message."""
        added: list[dict[str, str]] = []
        fake_context = SimpleNamespace(
            add_message=lambda role, content: added.append({"role": role, "content": content}),
            get_messages=lambda: added,
        )
        _register_session(app, "sess-post-3", context=fake_context)
        resp = client.post(
            "/sessions/sess-post-3/context/messages",
            json={"role": "assistant", "content": "Response text"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "assistant"
        assert data["content"] == "Response text"

    def test_add_message_no_context_returns_503(self, client: TestClient, app: FastAPI) -> None:
        """POST returns 503 when session has no context manager."""
        _register_session(app, "sess-post-4", context=None)
        resp = client.post(
            "/sessions/sess-post-4/context/messages",
            json={"role": "user", "content": "Hello"},
        )
        assert resp.status_code == 503


# -- PUT /sessions/{id}/context/messages --


@pytest.mark.unit
class TestSetMessages:
    """Tests for PUT /sessions/{id}/context/messages."""

    def test_session_not_found_returns_404(self, client: TestClient) -> None:
        """PUT /sessions/nonexistent/context/messages returns 404."""
        resp = client.put(
            "/sessions/nonexistent/context/messages",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/session-not-found"

    def test_set_messages_returns_200(self, client: TestClient, app: FastAPI) -> None:
        """PUT returns 200 OK with updated messages."""
        store: list[dict[str, str]] = []
        new_msgs = [{"role": "user", "content": "New message"}]

        def fake_set_messages(messages: list[dict[str, str]]) -> None:
            store.clear()
            store.extend(messages)

        fake_context = SimpleNamespace(
            set_messages=fake_set_messages,
            get_messages=lambda: store,
        )
        _register_session(app, "sess-put-1", context=fake_context)
        resp = client.put(
            "/sessions/sess-put-1/context/messages",
            json={"messages": new_msgs},
        )
        assert resp.status_code == 200

    def test_set_messages_calls_context_set_messages(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """PUT calls context.set_messages() with provided messages."""
        captured: list[object] = []

        def fake_set_messages(messages: list[dict[str, str]]) -> None:
            captured.extend(messages)

        fake_context = SimpleNamespace(
            set_messages=fake_set_messages,
            get_messages=lambda: captured,
        )
        _register_session(app, "sess-put-2", context=fake_context)
        client.put(
            "/sessions/sess-put-2/context/messages",
            json={"messages": [{"role": "system", "content": "You are helpful"}]},
        )
        assert len(captured) == 1

    def test_set_messages_response_contains_updated_messages(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """PUT response body includes the new messages list."""
        store: list[dict[str, str]] = []

        def fake_set_messages(messages: list[dict[str, str]]) -> None:
            store.clear()
            store.extend(messages)

        fake_context = SimpleNamespace(
            set_messages=fake_set_messages,
            get_messages=lambda: store,
        )
        _register_session(app, "sess-put-3", context=fake_context)
        resp = client.put(
            "/sessions/sess-put-3/context/messages",
            json={"messages": [{"role": "system", "content": "Be concise"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert data["total"] == 1
        assert data["messages"][0]["role"] == "system"

    def test_set_messages_no_context_returns_503(self, client: TestClient, app: FastAPI) -> None:
        """PUT returns 503 when session has no context manager."""
        _register_session(app, "sess-put-4", context=None)
        resp = client.put(
            "/sessions/sess-put-4/context/messages",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert resp.status_code == 503


# -- DELETE /sessions/{id}/context/messages --


@pytest.mark.unit
class TestClearMessages:
    """Tests for DELETE /sessions/{id}/context/messages."""

    def test_session_not_found_returns_404(self, client: TestClient) -> None:
        """DELETE /sessions/nonexistent/context/messages returns 404."""
        resp = client.delete("/sessions/nonexistent/context/messages")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/session-not-found"

    def test_clear_messages_returns_204(self, client: TestClient, app: FastAPI) -> None:
        """DELETE returns 204 No Content."""
        cleared: list[bool] = []
        fake_context = SimpleNamespace(clear=lambda: cleared.append(True))
        _register_session(app, "sess-del-1", context=fake_context)
        resp = client.delete("/sessions/sess-del-1/context/messages")
        assert resp.status_code == 204

    def test_clear_messages_calls_context_clear(self, client: TestClient, app: FastAPI) -> None:
        """DELETE calls context.clear()."""
        cleared: list[bool] = []
        fake_context = SimpleNamespace(clear=lambda: cleared.append(True))
        _register_session(app, "sess-del-2", context=fake_context)
        client.delete("/sessions/sess-del-2/context/messages")
        assert cleared == [True]

    def test_clear_messages_no_context_is_noop_204(self, client: TestClient, app: FastAPI) -> None:
        """DELETE is a graceful no-op (204) when session has no context."""
        _register_session(app, "sess-del-3", context=None)
        resp = client.delete("/sessions/sess-del-3/context/messages")
        assert resp.status_code == 204


# -- Router registration --


@pytest.mark.unit
class TestContextRouterRegistration:
    """Tests that context routes are registered in app.py."""

    def test_get_messages_route_registered(self) -> None:
        """GET /sessions/{session_id}/context/messages is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/sessions/{session_id}/context/messages" in route_paths

    def test_delete_messages_route_registered(self) -> None:
        """DELETE /sessions/{session_id}/context/messages is registered."""
        app = create_app()
        routes = [(r.path, list(r.methods)) for r in app.routes if hasattr(r, "methods")]  # type: ignore[union-attr]
        found = any(
            path == "/sessions/{session_id}/context/messages" and "DELETE" in methods
            for path, methods in routes
        )
        assert found, "DELETE /sessions/{session_id}/context/messages not registered"
