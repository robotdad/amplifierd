"""Tests for agent spawn/resume routes with session tree integration."""

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
    parent_id: str | None = None,
    bundle_name: str = "test-agent",
) -> SessionHandle:
    """Create a minimal SessionHandle with a fake session for testing."""
    fake_coordinator = SimpleNamespace(request_cancel=lambda immediate: None)
    fake_session = SimpleNamespace(
        session_id=session_id,
        parent_id=parent_id,
        coordinator=fake_coordinator,
        cleanup=_fake_cleanup,
        execute=_fake_execute,
    )
    return SessionHandle(
        session=fake_session,
        prepared_bundle=None,
        bundle_name=bundle_name,
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
    parent_id: str | None = None,
    bundle_name: str = "test-agent",
) -> SessionHandle:
    """Register a fake session in the session manager."""
    manager: SessionManager = app.state.session_manager
    event_bus = manager._event_bus  # noqa: SLF001
    handle = _make_handle(session_id, event_bus, parent_id=parent_id, bundle_name=bundle_name)
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


# -- POST /sessions/{id}/spawn --


@pytest.mark.unit
class TestSpawnEndpoint:
    """Tests for POST /sessions/{id}/spawn."""

    def test_spawn_parent_not_found_returns_404(self, client: TestClient) -> None:
        """POST /sessions/nonexistent/spawn returns 404."""
        resp = client.post(
            "/sessions/nonexistent/spawn",
            json={"agent": "my-agent", "instruction": "do something"},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/session-not-found"

    def test_spawn_returns_spawn_response(self, client: TestClient, app: FastAPI) -> None:
        """POST /sessions/{id}/spawn returns SpawnResponse with session_id and status."""
        _register_session(app, "parent-1")
        resp = client.post(
            "/sessions/parent-1/spawn",
            json={"agent": "my-agent", "instruction": "do something"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] is not None
        assert data["status"] is not None

    def test_spawn_registers_child_in_parent_children(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /sessions/{id}/spawn registers child session in parent's children dict."""
        _register_session(app, "parent-2")
        resp = client.post(
            "/sessions/parent-2/spawn",
            json={"agent": "my-agent", "instruction": "go"},
        )
        assert resp.status_code == 200
        child_id = resp.json()["session_id"]

        manager: SessionManager = app.state.session_manager
        parent_handle = manager.get("parent-2")
        assert parent_handle is not None
        assert child_id in parent_handle.children
        assert parent_handle.children[child_id] == "my-agent"

    def test_spawn_child_session_registered_in_manager(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /sessions/{id}/spawn registers the child session in SessionManager."""
        _register_session(app, "parent-3")
        resp = client.post(
            "/sessions/parent-3/spawn",
            json={"agent": "my-agent", "instruction": "go"},
        )
        assert resp.status_code == 200
        child_id = resp.json()["session_id"]

        manager: SessionManager = app.state.session_manager
        assert manager.get(child_id) is not None

    def test_spawn_child_has_correct_bundle_name(self, client: TestClient, app: FastAPI) -> None:
        """Spawned child session uses the agent name as its bundle_name."""
        _register_session(app, "parent-4")
        resp = client.post(
            "/sessions/parent-4/spawn",
            json={"agent": "special-agent", "instruction": "go"},
        )
        assert resp.status_code == 200
        child_id = resp.json()["session_id"]

        manager: SessionManager = app.state.session_manager
        child_handle = manager.get(child_id)
        assert child_handle is not None
        assert child_handle.bundle_name == "special-agent"

    def test_spawn_propagates_child_to_event_bus(self, client: TestClient, app: FastAPI) -> None:
        """POST /sessions/{id}/spawn registers child in EventBus tree."""
        _register_session(app, "parent-5")
        resp = client.post(
            "/sessions/parent-5/spawn",
            json={"agent": "my-agent", "instruction": "go"},
        )
        assert resp.status_code == 200
        child_id = resp.json()["session_id"]

        event_bus: EventBus = app.state.event_bus
        descendants = event_bus.get_descendants("parent-5")
        assert child_id in descendants


# -- POST /sessions/{id}/spawn/stream --


@pytest.mark.unit
class TestSpawnStreamEndpoint:
    """Tests for POST /sessions/{id}/spawn/stream."""

    def test_spawn_stream_parent_not_found_returns_404(self, client: TestClient) -> None:
        """POST /sessions/nonexistent/spawn/stream returns 404."""
        resp = client.post(
            "/sessions/nonexistent/spawn/stream",
            json={"agent": "my-agent", "instruction": "do something"},
        )
        assert resp.status_code == 404

    def test_spawn_stream_returns_202(self, client: TestClient, app: FastAPI) -> None:
        """POST /sessions/{id}/spawn/stream returns 202 Accepted."""
        _register_session(app, "parent-s1")
        resp = client.post(
            "/sessions/parent-s1/spawn/stream",
            json={"agent": "my-agent", "instruction": "go"},
        )
        assert resp.status_code == 202

    def test_spawn_stream_response_has_session_id(self, client: TestClient, app: FastAPI) -> None:
        """POST /sessions/{id}/spawn/stream response contains a session_id for tracking."""
        _register_session(app, "parent-s2")
        resp = client.post(
            "/sessions/parent-s2/spawn/stream",
            json={"agent": "my-agent", "instruction": "go"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["session_id"] is not None

    def test_spawn_stream_registers_child_in_parent(self, client: TestClient, app: FastAPI) -> None:
        """POST /sessions/{id}/spawn/stream registers child in parent before returning."""
        _register_session(app, "parent-s3")
        resp = client.post(
            "/sessions/parent-s3/spawn/stream",
            json={"agent": "my-agent", "instruction": "go"},
        )
        assert resp.status_code == 202
        child_id = resp.json()["session_id"]

        manager: SessionManager = app.state.session_manager
        parent_handle = manager.get("parent-s3")
        assert parent_handle is not None
        assert child_id in parent_handle.children


# -- POST /sessions/{id}/spawn/{child_id}/resume --


@pytest.mark.unit
class TestResumeChildEndpoint:
    """Tests for POST /sessions/{id}/spawn/{child_id}/resume."""

    def test_resume_parent_not_found_returns_404(self, client: TestClient) -> None:
        """POST /sessions/nonexistent/spawn/child/resume returns 404."""
        resp = client.post(
            "/sessions/nonexistent/spawn/child-1/resume",
            json={"instruction": "continue"},
        )
        assert resp.status_code == 404

    def test_resume_child_not_found_returns_404(self, client: TestClient, app: FastAPI) -> None:
        """POST /sessions/{id}/spawn/nonexistent/resume returns 404 when child not found."""
        _register_session(app, "parent-r1")
        resp = client.post(
            "/sessions/parent-r1/spawn/nonexistent-child/resume",
            json={"instruction": "continue"},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/session-not-found"

    def test_resume_returns_spawn_response(self, client: TestClient, app: FastAPI) -> None:
        """POST /sessions/{id}/spawn/{child_id}/resume returns SpawnResponse."""
        _register_session(app, "parent-r2")
        child_handle = _register_session(app, "child-r2", parent_id="parent-r2")
        child_handle._children  # noqa: B018 -- just to confirm handle exists

        resp = client.post(
            "/sessions/parent-r2/spawn/child-r2/resume",
            json={"instruction": "keep going"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "child-r2"
        assert data["status"] is not None

    def test_resume_increments_child_turn_count(self, client: TestClient, app: FastAPI) -> None:
        """Resuming a child agent increments its turn_count."""
        _register_session(app, "parent-r3")
        child_handle = _register_session(app, "child-r3", parent_id="parent-r3")
        assert child_handle.turn_count == 0

        resp = client.post(
            "/sessions/parent-r3/spawn/child-r3/resume",
            json={"instruction": "go again"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["turn_count"] == 1


# -- GET /sessions/{id}/agents --


@pytest.mark.unit
class TestListAgentsEndpoint:
    """Tests for GET /sessions/{id}/agents."""

    def test_list_agents_session_not_found_returns_404(self, client: TestClient) -> None:
        """GET /sessions/nonexistent/agents returns 404."""
        resp = client.get("/sessions/nonexistent/agents")
        assert resp.status_code == 404

    def test_list_agents_returns_empty_when_no_registry(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """GET /sessions/{id}/agents returns empty agents dict when no bundle registry."""
        _register_session(app, "sess-a1")
        app.state.bundle_registry = None
        resp = client.get("/sessions/sess-a1/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert data["agents"] == {}

    def test_list_agents_reads_from_bundle_registry(self, client: TestClient, app: FastAPI) -> None:
        """GET /sessions/{id}/agents returns agents from bundle registry when available."""
        _register_session(app, "sess-a2")

        # Fake bundle registry with list_agents()
        fake_registry = SimpleNamespace(
            list_agents=lambda: {
                "code-agent": {"description": "Writes code", "model_role": "coding"},
                "review-agent": {"description": "Reviews code", "model_role": None},
            }
        )
        app.state.bundle_registry = fake_registry

        resp = client.get("/sessions/sess-a2/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "code-agent" in data["agents"]
        assert data["agents"]["code-agent"]["description"] == "Writes code"
        assert data["agents"]["code-agent"]["model_role"] == "coding"
        assert "review-agent" in data["agents"]

    def test_list_agents_tolerates_registry_failure(self, client: TestClient, app: FastAPI) -> None:
        """GET /sessions/{id}/agents returns empty dict if registry.list_agents() raises."""
        _register_session(app, "sess-a3")

        def _bad_list() -> None:
            raise RuntimeError("registry broken")

        app.state.bundle_registry = SimpleNamespace(list_agents=_bad_list)
        resp = client.get("/sessions/sess-a3/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agents"] == {}


# -- Router registration --


@pytest.mark.unit
class TestAgentsRouterRegistration:
    """Tests for agents router registration in app.py."""

    def test_spawn_route_registered(self) -> None:
        """The agents router is registered with spawn route."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/sessions/{session_id}/spawn" in route_paths

    def test_spawn_stream_route_registered(self) -> None:
        """The agents router is registered with spawn/stream route."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/sessions/{session_id}/spawn/stream" in route_paths

    def test_resume_route_registered(self) -> None:
        """The agents router is registered with spawn/{child_id}/resume route."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/sessions/{session_id}/spawn/{child_id}/resume" in route_paths

    def test_agents_list_route_registered(self) -> None:
        """The agents router is registered with GET agents route."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/sessions/{session_id}/agents" in route_paths
