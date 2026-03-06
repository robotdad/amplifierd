"""Tests for health and info endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from amplifierd.app import create_app


@pytest.fixture()
def client() -> TestClient:
    """Create a test client from the app factory."""
    app = create_app()
    return TestClient(app)


@pytest.mark.unit
class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_200(self, client: TestClient) -> None:
        """GET /health returns 200 with status=healthy, version, uptime_seconds, active_sessions."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0
        assert "active_sessions" in data
        assert isinstance(data["active_sessions"], int)
        assert data["active_sessions"] >= 0

    def test_health_without_session_manager(self, client: TestClient) -> None:
        """GET /health returns active_sessions=0 when session_manager is None."""
        client.app.state.session_manager = None  # type: ignore[union-attr]
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_sessions"] == 0

    def test_health_has_rust_engine_field(self, client: TestClient) -> None:
        """GET /health includes rust_engine boolean field."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "rust_engine" in data
        assert isinstance(data["rust_engine"], bool)


@pytest.mark.unit
class TestInfoEndpoint:
    """Tests for GET /info."""

    def test_info_returns_200(self, client: TestClient) -> None:
        """GET /info returns 200 with version and amplifier_core_version."""
        resp = client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "amplifier_core_version" in data

    def test_info_has_capabilities(self, client: TestClient) -> None:
        """GET /info includes capabilities list."""
        resp = client.get("/info")
        data = resp.json()
        assert "capabilities" in data
        caps = data["capabilities"]
        assert isinstance(caps, list)
        for expected in (
            "streaming",
            "approval",
            "cancellation",
            "hot_mount",
            "fork",
            "spawn",
        ):
            assert expected in caps

    def test_info_has_module_types(self, client: TestClient) -> None:
        """GET /info includes module_types list."""
        resp = client.get("/info")
        data = resp.json()
        assert "module_types" in data
        mtypes = data["module_types"]
        assert isinstance(mtypes, list)
        for expected in ("orchestrator", "provider", "tool", "hook", "context", "resolver"):
            assert expected in mtypes


@pytest.mark.unit
class TestOpenAPIEndpoint:
    """Tests for OpenAPI schema availability."""

    def test_openapi_json_returns_200(self, client: TestClient) -> None:
        """GET /openapi.json returns 200 with a valid OpenAPI schema."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "openapi" in schema
        assert schema["openapi"].startswith("3.")
        assert schema["info"]["title"] == "amplifierd"
        assert schema["info"]["version"] == "0.1.0"
        assert "paths" in schema
        assert len(schema["paths"]) > 0

    def test_openapi_includes_all_route_groups(self, client: TestClient) -> None:
        """The OpenAPI schema includes paths for all major route groups."""
        resp = client.get("/openapi.json")
        schema = resp.json()
        paths = list(schema["paths"].keys())
        # Spot-check key endpoints from each route module
        assert "/health" in paths
        assert "/sessions" in paths
        assert "/events" in paths
        assert "/bundles" in paths
        assert "/modules" in paths

    def test_docs_endpoint_returns_200(self, client: TestClient) -> None:
        """GET /docs (Swagger UI) returns 200."""
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_endpoint_returns_200(self, client: TestClient) -> None:
        """GET /redoc returns 200."""
        resp = client.get("/redoc")
        assert resp.status_code == 200
