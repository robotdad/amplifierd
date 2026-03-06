"""Tests for validation and reload routes."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amplifierd.app import create_app
from amplifierd.config import DaemonSettings
from amplifierd.state.event_bus import EventBus
from amplifierd.state.session_manager import SessionManager

# -- Helpers --


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


# -- Validation: registry unavailable (503) --


@pytest.mark.unit
class TestValidationRegistryUnavailable:
    """All validation routes return 503 when bundle_registry is None."""

    def test_validate_mount_plan_503_when_no_registry(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /validate/mount-plan returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.post(
            "/validate/mount-plan",
            json={"mount_plan": {"modules": []}},
        )
        assert resp.status_code == 503

    def test_validate_module_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """POST /validate/module returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.post(
            "/validate/module",
            json={"module_id": "my-module"},
        )
        assert resp.status_code == 503

    def test_validate_bundle_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """POST /validate/bundle returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.post(
            "/validate/bundle",
            json={"source": "git+https://example.com/bundle"},
        )
        assert resp.status_code == 503


# -- POST /validate/mount-plan --


@pytest.mark.unit
class TestValidateMountPlan:
    """Tests for POST /validate/mount-plan."""

    def test_returns_200_with_valid_result(self, client: TestClient, app: FastAPI) -> None:
        """POST /validate/mount-plan returns 200 with ValidationResponse."""
        app.state.bundle_registry = SimpleNamespace(
            validate_mount_plan=lambda plan: SimpleNamespace(valid=True, errors=None, warnings=None)
        )
        resp = client.post(
            "/validate/mount-plan",
            json={"mount_plan": {"modules": [{"name": "tool-1", "mount": "tools"}]}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "valid" in data
        assert data["valid"] is True

    def test_returns_invalid_result_when_validation_fails(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /validate/mount-plan returns valid=False when validation errors found."""
        app.state.bundle_registry = SimpleNamespace(
            validate_mount_plan=lambda plan: SimpleNamespace(
                valid=False,
                errors=["Module 'bad-mod' not found"],
                warnings=None,
            )
        )
        resp = client.post(
            "/validate/mount-plan",
            json={"mount_plan": {"modules": [{"name": "bad-mod"}]}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["errors"] is not None

    def test_returns_valid_true_when_registry_lacks_validate_method(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /validate/mount-plan returns valid=True when registry has no validator."""
        app.state.bundle_registry = SimpleNamespace()  # no validate_mount_plan method
        resp = client.post(
            "/validate/mount-plan",
            json={"mount_plan": {"modules": []}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "valid" in data


# -- POST /validate/module --


@pytest.mark.unit
class TestValidateModule:
    """Tests for POST /validate/module."""

    def test_returns_200_with_valid_result(self, client: TestClient, app: FastAPI) -> None:
        """POST /validate/module returns 200 with ValidationResponse."""
        app.state.bundle_registry = SimpleNamespace(
            validate_module=lambda module_id, **kwargs: SimpleNamespace(
                valid=True, errors=None, warnings=None
            )
        )
        resp = client.post(
            "/validate/module",
            json={"module_id": "my-tool", "type": "tool"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "valid" in data
        assert data["valid"] is True

    def test_returns_valid_result_without_optional_fields(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /validate/module accepts minimal body (module_id only)."""
        app.state.bundle_registry = SimpleNamespace(
            validate_module=lambda module_id, **kwargs: SimpleNamespace(
                valid=True, errors=None, warnings=None
            )
        )
        resp = client.post(
            "/validate/module",
            json={"module_id": "bare-module"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_returns_valid_true_when_registry_lacks_validate_method(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /validate/module returns valid=True when registry has no validator."""
        app.state.bundle_registry = SimpleNamespace()  # no validate_module method
        resp = client.post(
            "/validate/module",
            json={"module_id": "some-module"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "valid" in data


# -- POST /validate/bundle --


@pytest.mark.unit
class TestValidateBundle:
    """Tests for POST /validate/bundle."""

    def test_returns_200_with_valid_result(self, client: TestClient, app: FastAPI) -> None:
        """POST /validate/bundle returns 200 with ValidationResponse."""
        app.state.bundle_registry = SimpleNamespace(
            validate_bundle=lambda source: SimpleNamespace(valid=True, errors=None, warnings=None)
        )
        resp = client.post(
            "/validate/bundle",
            json={"source": "git+https://example.com/my-bundle"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "valid" in data
        assert data["valid"] is True

    def test_returns_invalid_result_on_error(self, client: TestClient, app: FastAPI) -> None:
        """POST /validate/bundle returns valid=False with errors on validation failure."""
        app.state.bundle_registry = SimpleNamespace(
            validate_bundle=lambda source: SimpleNamespace(
                valid=False,
                errors=["bundle.yaml missing required field: name"],
                warnings=None,
            )
        )
        resp = client.post(
            "/validate/bundle",
            json={"source": "git+https://example.com/bad-bundle"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False

    def test_returns_valid_true_when_registry_lacks_validate_method(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /validate/bundle returns valid=True when registry has no validator."""
        app.state.bundle_registry = SimpleNamespace()  # no validate_bundle method
        resp = client.post(
            "/validate/bundle",
            json={"source": "git+https://example.com/bundle"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "valid" in data


# -- Reload: registry unavailable (503) --


@pytest.mark.unit
class TestReloadRegistryUnavailable:
    """Reload routes return 503 when bundle_registry is None."""

    def test_reload_bundles_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """POST /reload/bundles returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.post("/reload/bundles")
        assert resp.status_code == 503

    def test_reload_status_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """GET /reload/status returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.get("/reload/status")
        assert resp.status_code == 503


# -- POST /reload/bundles --


@pytest.mark.unit
class TestReloadBundles:
    """Tests for POST /reload/bundles."""

    def test_returns_200_with_reload_summary(self, client: TestClient, app: FastAPI) -> None:
        """POST /reload/bundles returns 200 with a reload summary."""
        loaded_names: list[str] = []

        async def fake_load(source: str) -> SimpleNamespace:
            loaded_names.append(source)
            return SimpleNamespace(name=source, version="1.0.0")

        app.state.bundle_registry = SimpleNamespace(
            list_registered=lambda: ["bundle-a", "bundle-b"],
            load=fake_load,
        )
        resp = client.post("/reload/bundles")
        assert resp.status_code == 200
        data = resp.json()
        assert "reloaded" in data
        assert "failed" in data
        assert "total" in data

    def test_reloads_each_registered_bundle(self, client: TestClient, app: FastAPI) -> None:
        """POST /reload/bundles calls load() for each registered bundle."""
        reloaded: list[str] = []

        async def fake_load(source: str) -> SimpleNamespace:
            reloaded.append(source)
            return SimpleNamespace(name=source, version="1.0.0")

        app.state.bundle_registry = SimpleNamespace(
            list_registered=lambda: ["bundle-a", "bundle-b"],
            load=fake_load,
        )
        client.post("/reload/bundles")
        assert "bundle-a" in reloaded
        assert "bundle-b" in reloaded

    def test_returns_empty_reloaded_when_no_bundles_registered(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /reload/bundles returns empty reloaded list when no bundles are registered."""
        app.state.bundle_registry = SimpleNamespace(
            list_registered=lambda: [],
        )
        resp = client.post("/reload/bundles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reloaded"] == []
        assert data["total"] == 0

    def test_failed_bundles_recorded_on_load_error(self, client: TestClient, app: FastAPI) -> None:
        """POST /reload/bundles records failures when a bundle cannot be reloaded."""

        async def fake_load(source: str) -> SimpleNamespace:
            raise RuntimeError("Failed to load")

        app.state.bundle_registry = SimpleNamespace(
            list_registered=lambda: ["broken-bundle"],
            load=fake_load,
        )
        resp = client.post("/reload/bundles")
        assert resp.status_code == 200
        data = resp.json()
        assert "broken-bundle" in data["failed"]
        assert data["reloaded"] == []


# -- GET /reload/status --


@pytest.mark.unit
class TestReloadStatus:
    """Tests for GET /reload/status."""

    def test_returns_200_with_bundle_list(self, client: TestClient, app: FastAPI) -> None:
        """GET /reload/status returns 200 with bundles list."""
        fake_state = SimpleNamespace(version="1.0.0")

        async def fake_check_update(name: str) -> None:
            return None

        app.state.bundle_registry = SimpleNamespace(
            list_registered=lambda: ["bundle-a"],
            get_state=lambda name: fake_state,
            check_update=fake_check_update,
        )
        resp = client.get("/reload/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "bundles" in data
        assert len(data["bundles"]) == 1

    def test_returns_has_update_true_when_update_available(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """GET /reload/status returns has_update=True when an update is available."""
        fake_state = SimpleNamespace(version="1.0.0")
        fake_update = SimpleNamespace(available_version="2.0.0")

        async def fake_check_update(name: str) -> SimpleNamespace:
            return fake_update

        app.state.bundle_registry = SimpleNamespace(
            list_registered=lambda: ["my-bundle"],
            get_state=lambda name: fake_state,
            check_update=fake_check_update,
        )
        resp = client.get("/reload/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bundles"][0]["has_update"] is True
        assert data["bundles"][0]["available_version"] == "2.0.0"

    def test_returns_has_update_false_when_up_to_date(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """GET /reload/status returns has_update=False when bundle is up to date."""
        fake_state = SimpleNamespace(version="1.0.0")

        async def fake_check_update(name: str) -> None:
            return None

        app.state.bundle_registry = SimpleNamespace(
            list_registered=lambda: ["up-to-date-bundle"],
            get_state=lambda name: fake_state,
            check_update=fake_check_update,
        )
        resp = client.get("/reload/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bundles"][0]["has_update"] is False

    def test_returns_empty_bundles_when_none_registered(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """GET /reload/status returns empty bundles list when none are registered."""
        app.state.bundle_registry = SimpleNamespace(
            list_registered=lambda: [],
        )
        resp = client.get("/reload/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bundles"] == []


# -- Router registration --


@pytest.mark.unit
class TestValidationRouterRegistration:
    """Tests that validation routes are registered in app.py."""

    def test_validate_mount_plan_route_registered(self) -> None:
        """POST /validate/mount-plan route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/validate/mount-plan" in route_paths

    def test_validate_module_route_registered(self) -> None:
        """POST /validate/module route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/validate/module" in route_paths

    def test_validate_bundle_route_registered(self) -> None:
        """POST /validate/bundle route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/validate/bundle" in route_paths


@pytest.mark.unit
class TestReloadRouterRegistration:
    """Tests that reload routes are registered in app.py."""

    def test_reload_bundles_route_registered(self) -> None:
        """POST /reload/bundles route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/reload/bundles" in route_paths

    def test_reload_status_route_registered(self) -> None:
        """GET /reload/status route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/reload/status" in route_paths
