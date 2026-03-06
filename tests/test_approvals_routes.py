"""Tests for approval routes with asyncio.Future-based gates."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amplifierd.app import create_app
from amplifierd.config import DaemonSettings
from amplifierd.routes.approvals import PendingApproval
from amplifierd.state.event_bus import EventBus
from amplifierd.state.session_handle import SessionHandle
from amplifierd.state.session_manager import SessionManager

# -- Helpers --


async def _fake_cleanup() -> None:
    """No-op async cleanup for fake sessions."""


def _make_handle(session_id: str, event_bus: EventBus) -> SessionHandle:
    """Create a minimal SessionHandle with a fake session for testing."""
    fake_coordinator = SimpleNamespace(request_cancel=lambda immediate: None)
    fake_session = SimpleNamespace(
        session_id=session_id,
        parent_id=None,
        coordinator=fake_coordinator,
        cleanup=_fake_cleanup,
    )
    return SessionHandle(
        session=fake_session,
        prepared_bundle=None,
        bundle_name="test-agent",
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
    app.state.pending_approvals = {}
    return app


def _register_session(app: FastAPI, session_id: str) -> SessionHandle:
    """Register a fake session in the session manager."""
    manager: SessionManager = app.state.session_manager
    event_bus = manager._event_bus  # noqa: SLF001
    handle = _make_handle(session_id, event_bus)
    manager._sessions[session_id] = handle  # noqa: SLF001
    return handle


def _add_pending_approval(
    app: FastAPI, session_id: str, request_id: str, data: dict[str, Any] | None = None
) -> PendingApproval:
    """Add a PendingApproval to app.state for testing."""
    if not hasattr(app.state, "pending_approvals"):
        app.state.pending_approvals = {}
    approval = PendingApproval(request_id=request_id, session_id=session_id, data=data)
    app.state.pending_approvals.setdefault(session_id, {})[request_id] = approval
    return approval


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


# -- GET /sessions/{id}/approvals --


@pytest.mark.unit
class TestListApprovalsEndpoint:
    """Tests for GET /sessions/{id}/approvals."""

    def test_list_empty_returns_empty_list(self, client: TestClient, app: FastAPI) -> None:
        """GET /sessions/{id}/approvals returns empty list when no approvals pending."""
        _register_session(app, "s1")
        resp = client.get("/sessions/s1/approvals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["approvals"] == []
        assert data["total"] == 0

    def test_list_session_not_found_returns_404(self, client: TestClient) -> None:
        """GET /sessions/{id}/approvals returns 404 for nonexistent session."""
        resp = client.get("/sessions/nonexistent/approvals")
        assert resp.status_code == 404

    def test_list_returns_pending_approvals(self, client: TestClient, app: FastAPI) -> None:
        """GET /sessions/{id}/approvals returns all pending (unresolved) approvals."""
        _register_session(app, "s1")
        _add_pending_approval(app, "s1", "r1", data={"tool": "rm"})
        _add_pending_approval(app, "s1", "r2", data={"tool": "write"})

        resp = client.get("/sessions/s1/approvals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        request_ids = {a["request_id"] for a in data["approvals"]}
        assert request_ids == {"r1", "r2"}


# -- POST /sessions/{id}/approvals/{request_id} --


@pytest.mark.unit
class TestRespondToApprovalEndpoint:
    """Tests for POST /sessions/{id}/approvals/{request_id}."""

    def test_resolves_approval_future(self, client: TestClient, app: FastAPI) -> None:
        """POST resolves the asyncio.Future for the given request_id."""
        _register_session(app, "s1")
        approval = _add_pending_approval(app, "s1", "r1")

        resp = client.post(
            "/sessions/s1/approvals/r1",
            json={"approved": True, "message": "looks good"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["request_id"] == "r1"
        assert data["status"] == "resolved"
        assert approval.resolved is True

    def test_unknown_request_id_returns_404(self, client: TestClient, app: FastAPI) -> None:
        """POST returns 404 for unknown request_id."""
        _register_session(app, "s1")
        resp = client.post(
            "/sessions/s1/approvals/unknown",
            json={"approved": True},
        )
        assert resp.status_code == 404

    def test_session_not_found_returns_404(self, client: TestClient) -> None:
        """POST returns 404 for nonexistent session."""
        resp = client.post(
            "/sessions/nonexistent/approvals/r1",
            json={"approved": True},
        )
        assert resp.status_code == 404


# -- Router registration --


@pytest.mark.unit
class TestApprovalRouterRegistration:
    """Tests for approval router registration in app.py."""

    def test_approvals_router_registered_in_app(self) -> None:
        """The approvals router is registered and approval routes exist."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/sessions/{session_id}/approvals" in route_paths
        assert "/sessions/{session_id}/approvals/{request_id}" in route_paths

    def test_approvals_router_registered_after_events(self) -> None:
        """The approvals router is registered after the events router in app.py."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        events_idx = route_paths.index("/events")
        approval_indices = [i for i, p in enumerate(route_paths) if "approvals" in p]
        assert len(approval_indices) > 0
        assert all(idx > events_idx for idx in approval_indices)
