"""Tests for module management routes."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

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


def _make_module(
    module_id: str = "mod-1",
    name: str = "my-module",
    version: str = "1.0.0",
    type_: str | None = "tool",
    mount_point: str | None = None,
    description: str | None = None,
) -> SimpleNamespace:
    """Create a minimal fake module for testing."""
    return SimpleNamespace(
        id=module_id,
        name=name,
        version=version,
        type=type_,
        mount_point=mount_point,
        description=description,
    )


def _make_session(
    session_id: str,
    event_bus: EventBus,
    *,
    coordinator: Any | None = None,
) -> SessionHandle:
    """Create a minimal SessionHandle with optional coordinator override."""
    if coordinator is None:
        coordinator = SimpleNamespace(request_cancel=lambda immediate: None)
    fake_session = SimpleNamespace(
        session_id=session_id,
        parent_id=None,
        coordinator=coordinator,
        cleanup=_fake_cleanup,
        execute=_fake_execute,
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
    app.state.module_coordinator = None
    return app


def _register_session(
    app: FastAPI,
    session_id: str,
    *,
    coordinator: Any | None = None,
) -> SessionHandle:
    """Register a fake session in the session manager."""
    manager: SessionManager = app.state.session_manager
    event_bus = manager._event_bus  # noqa: SLF001
    handle = _make_session(session_id, event_bus, coordinator=coordinator)
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


# -- GET /modules --


@pytest.mark.unit
class TestListModules:
    """Tests for GET /modules."""

    def test_returns_empty_list_when_no_coordinator(self, client: TestClient, app: FastAPI) -> None:
        """GET /modules returns empty list when no module_coordinator in state."""
        app.state.module_coordinator = None
        resp = client.get("/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["modules"] == []

    def test_returns_modules_from_coordinator(self, client: TestClient, app: FastAPI) -> None:
        """GET /modules returns modules from the module_coordinator."""
        fake_mod = _make_module("mod-1", "my-module")
        app.state.module_coordinator = SimpleNamespace(
            list_available=lambda: [fake_mod],
        )
        resp = client.get("/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["modules"]) == 1
        assert data["modules"][0]["id"] == "mod-1"
        assert data["modules"][0]["name"] == "my-module"

    def test_returns_empty_on_coordinator_failure(self, client: TestClient, app: FastAPI) -> None:
        """GET /modules returns empty list gracefully when coordinator.list_available() raises."""

        def _bad_list() -> None:
            raise RuntimeError("coordinator broken")

        app.state.module_coordinator = SimpleNamespace(list_available=_bad_list)
        resp = client.get("/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["modules"] == []


# -- GET /modules/{module_id} --


@pytest.mark.unit
class TestGetModuleDetail:
    """Tests for GET /modules/{module_id}."""

    def test_returns_404_when_coordinator_unavailable(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """GET /modules/{id} returns 404 when no module_coordinator configured."""
        app.state.module_coordinator = None
        resp = client.get("/modules/some-module")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/module-not-found"

    def test_returns_404_when_module_not_found(self, client: TestClient, app: FastAPI) -> None:
        """GET /modules/{id} returns 404 when module not found in coordinator."""
        app.state.module_coordinator = SimpleNamespace(
            get_module=lambda module_id: None,
        )
        resp = client.get("/modules/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/module-not-found"

    def test_returns_module_detail(self, client: TestClient, app: FastAPI) -> None:
        """GET /modules/{id} returns ModuleSummary for a known module."""
        fake_mod = _make_module("tool-1", "my-tool", description="A useful tool")
        app.state.module_coordinator = SimpleNamespace(
            get_module=lambda module_id: fake_mod,
        )
        resp = client.get("/modules/tool-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "tool-1"
        assert data["name"] == "my-tool"
        assert data["description"] == "A useful tool"


# -- POST /sessions/{id}/modules/mount --


@pytest.mark.unit
class TestMountModule:
    """Tests for POST /sessions/{id}/modules/mount."""

    def test_session_not_found_returns_404(self, client: TestClient) -> None:
        """POST /sessions/nonexistent/modules/mount returns 404."""
        resp = client.post(
            "/sessions/nonexistent/modules/mount",
            json={"module_id": "my-module"},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/session-not-found"

    def test_mount_returns_module_summary(self, client: TestClient, app: FastAPI) -> None:
        """POST /sessions/{id}/modules/mount returns ModuleSummary on success."""
        fake_mod = _make_module("mod-m1", "mounted-module", mount_point="tools")
        fake_coordinator = SimpleNamespace(
            request_cancel=lambda immediate: None,
            mount=lambda module_id, config=None, source=None: fake_mod,
        )
        _register_session(app, "sess-mount-1", coordinator=fake_coordinator)
        resp = client.post(
            "/sessions/sess-mount-1/modules/mount",
            json={"module_id": "mod-m1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "mod-m1"
        assert data["name"] == "mounted-module"

    def test_mount_calls_coordinator_mount(self, client: TestClient, app: FastAPI) -> None:
        """POST mount calls coordinator.mount() with the correct module_id."""
        called_with: list[str] = []

        def fake_mount(module_id: str, config: Any = None, source: Any = None) -> SimpleNamespace:
            called_with.append(module_id)
            return _make_module(module_id, module_id)

        fake_coordinator = SimpleNamespace(
            request_cancel=lambda immediate: None,
            mount=fake_mount,
        )
        _register_session(app, "sess-mount-2", coordinator=fake_coordinator)
        client.post(
            "/sessions/sess-mount-2/modules/mount",
            json={"module_id": "special-mod"},
        )
        assert "special-mod" in called_with

    def test_mount_no_coordinator_mount_method_returns_503(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST mount returns 503 when session coordinator lacks mount method."""
        # Coordinator only has request_cancel, no mount
        fake_coordinator = SimpleNamespace(request_cancel=lambda immediate: None)
        _register_session(app, "sess-mount-3", coordinator=fake_coordinator)
        resp = client.post(
            "/sessions/sess-mount-3/modules/mount",
            json={"module_id": "my-mod"},
        )
        assert resp.status_code == 503


# -- POST /sessions/{id}/modules/unmount --


@pytest.mark.unit
class TestUnmountModule:
    """Tests for POST /sessions/{id}/modules/unmount."""

    def test_session_not_found_returns_404(self, client: TestClient) -> None:
        """POST /sessions/nonexistent/modules/unmount returns 404."""
        resp = client.post(
            "/sessions/nonexistent/modules/unmount",
            json={"name": "my-module"},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/session-not-found"

    def test_unmount_returns_204(self, client: TestClient, app: FastAPI) -> None:
        """POST /sessions/{id}/modules/unmount returns 204 on success."""
        fake_coordinator = SimpleNamespace(
            request_cancel=lambda immediate: None,
            unmount=lambda name=None, mount_point=None: None,
        )
        _register_session(app, "sess-unmount-1", coordinator=fake_coordinator)
        resp = client.post(
            "/sessions/sess-unmount-1/modules/unmount",
            json={"name": "my-module"},
        )
        assert resp.status_code == 204

    def test_unmount_calls_coordinator_unmount(self, client: TestClient, app: FastAPI) -> None:
        """POST unmount calls coordinator.unmount() with correct args."""
        called: list[dict[str, Any]] = []

        def fake_unmount(name: str | None = None, mount_point: str | None = None) -> None:
            called.append({"name": name, "mount_point": mount_point})

        fake_coordinator = SimpleNamespace(
            request_cancel=lambda immediate: None,
            unmount=fake_unmount,
        )
        _register_session(app, "sess-unmount-2", coordinator=fake_coordinator)
        client.post(
            "/sessions/sess-unmount-2/modules/unmount",
            json={"name": "target-module"},
        )
        assert len(called) == 1
        assert called[0]["name"] == "target-module"

    def test_unmount_no_coordinator_unmount_method_returns_503(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST unmount returns 503 when session coordinator lacks unmount method."""
        fake_coordinator = SimpleNamespace(request_cancel=lambda immediate: None)
        _register_session(app, "sess-unmount-3", coordinator=fake_coordinator)
        resp = client.post(
            "/sessions/sess-unmount-3/modules/unmount",
            json={"name": "some-module"},
        )
        assert resp.status_code == 503


# -- GET /sessions/{id}/modules --


@pytest.mark.unit
class TestListSessionModules:
    """Tests for GET /sessions/{id}/modules."""

    def test_session_not_found_returns_404(self, client: TestClient) -> None:
        """GET /sessions/nonexistent/modules returns 404."""
        resp = client.get("/sessions/nonexistent/modules")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/session-not-found"

    def test_returns_empty_list_when_no_coordinator_method(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """GET /sessions/{id}/modules returns empty list when coordinator lacks list_mounted."""
        fake_coordinator = SimpleNamespace(request_cancel=lambda immediate: None)
        _register_session(app, "sess-list-1", coordinator=fake_coordinator)
        resp = client.get("/sessions/sess-list-1/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["modules"] == []

    def test_returns_mounted_modules(self, client: TestClient, app: FastAPI) -> None:
        """GET /sessions/{id}/modules returns list of mounted modules."""
        fake_mod = _make_module("mod-l1", "listed-module", mount_point="tools")
        fake_coordinator = SimpleNamespace(
            request_cancel=lambda immediate: None,
            list_mounted=lambda: [fake_mod],
        )
        _register_session(app, "sess-list-2", coordinator=fake_coordinator)
        resp = client.get("/sessions/sess-list-2/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["modules"]) == 1
        assert data["modules"][0]["id"] == "mod-l1"
        assert data["modules"][0]["name"] == "listed-module"

    def test_returns_empty_on_list_mounted_failure(self, client: TestClient, app: FastAPI) -> None:
        """GET /sessions/{id}/modules returns empty list gracefully on coordinator failure."""

        def _bad_list() -> None:
            raise RuntimeError("list failed")

        fake_coordinator = SimpleNamespace(
            request_cancel=lambda immediate: None,
            list_mounted=_bad_list,
        )
        _register_session(app, "sess-list-3", coordinator=fake_coordinator)
        resp = client.get("/sessions/sess-list-3/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["modules"] == []


# -- Router registration --


@pytest.mark.unit
class TestModulesRouterRegistration:
    """Tests that module routes are registered in app.py."""

    def test_list_modules_route_registered(self) -> None:
        """GET /modules is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/modules" in route_paths

    def test_get_module_detail_route_registered(self) -> None:
        """GET /modules/{module_id} is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/modules/{module_id}" in route_paths

    def test_mount_module_route_registered(self) -> None:
        """POST /sessions/{session_id}/modules/mount is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/sessions/{session_id}/modules/mount" in route_paths

    def test_unmount_module_route_registered(self) -> None:
        """POST /sessions/{session_id}/modules/unmount is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/sessions/{session_id}/modules/unmount" in route_paths

    def test_list_session_modules_route_registered(self) -> None:
        """GET /sessions/{session_id}/modules is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/sessions/{session_id}/modules" in route_paths
