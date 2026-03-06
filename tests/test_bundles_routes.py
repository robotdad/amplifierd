"""Tests for bundle management routes."""

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


def _make_fake_bundle(name: str = "test-bundle") -> SimpleNamespace:
    """Create a minimal fake bundle for testing."""

    async def _noop_prepare(install_deps: bool = True) -> SimpleNamespace:
        return SimpleNamespace()

    return SimpleNamespace(
        name=name,
        version="1.0.0",
        description="A test bundle",
        includes=[],
        providers=[],
        tools=[],
        hooks=[],
        agents={},
        context={},
        prepare=_noop_prepare,
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


# -- Registry unavailable (503) --


@pytest.mark.unit
class TestRegistryUnavailable:
    """All bundle routes return 503 when bundle_registry is None.

    Note: state must be forced to None inside each test because the app lifespan
    runs on TestClient entry and may initialise a real BundleRegistry.
    """

    def test_list_bundles_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """GET /bundles returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.get("/bundles")
        assert resp.status_code == 503

    def test_register_bundle_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """POST /bundles/register returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.post(
            "/bundles/register",
            json={"name": "test", "uri": "git+https://example.com"},
        )
        assert resp.status_code == 503

    def test_delete_bundle_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """DELETE /bundles/{name} returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.delete("/bundles/test-bundle")
        assert resp.status_code == 503

    def test_load_bundle_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """POST /bundles/load returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.post("/bundles/load", json={"source": "git+https://example.com"})
        assert resp.status_code == 503

    def test_prepare_bundle_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """POST /bundles/prepare returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.post(
            "/bundles/prepare",
            json={"source": "git+https://example.com"},
        )
        assert resp.status_code == 503

    def test_compose_bundles_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """POST /bundles/compose returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.post("/bundles/compose", json={"bundles": ["a", "b"]})
        assert resp.status_code == 503

    def test_check_updates_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """POST /bundles/{name}/check-updates returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.post("/bundles/foundation/check-updates")
        assert resp.status_code == 503

    def test_update_bundle_503_when_no_registry(self, client: TestClient, app: FastAPI) -> None:
        """POST /bundles/{name}/update returns 503 when registry unavailable."""
        app.state.bundle_registry = None
        resp = client.post("/bundles/foundation/update")
        assert resp.status_code == 503


# -- GET /bundles --


@pytest.mark.unit
class TestListBundlesEndpoint:
    """Tests for GET /bundles."""

    def test_list_bundles_returns_empty_when_no_bundles(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """GET /bundles returns empty list when no bundles registered."""
        app.state.bundle_registry = SimpleNamespace(
            list_registered=lambda: [],
            get_state=lambda name=None: {},
        )
        resp = client.get("/bundles")
        assert resp.status_code == 200
        data = resp.json()
        assert "bundles" in data
        assert data["bundles"] == []

    def test_list_bundles_returns_registered_bundles(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """GET /bundles returns registered bundles with name and URI."""
        fake_state = SimpleNamespace(
            uri="git+https://example.com/foundation",
            name="foundation",
            version="1.0.0",
            loaded_at=None,
        )
        app.state.bundle_registry = SimpleNamespace(
            list_registered=lambda: ["foundation"],
            get_state=lambda name=None: {"foundation": fake_state} if name is None else fake_state,
        )
        resp = client.get("/bundles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["bundles"]) == 1
        assert data["bundles"][0]["name"] == "foundation"
        assert data["bundles"][0]["uri"] == "git+https://example.com/foundation"


# -- POST /bundles/register --


@pytest.mark.unit
class TestRegisterBundleEndpoint:
    """Tests for POST /bundles/register."""

    def test_register_bundle_returns_201(self, client: TestClient, app: FastAPI) -> None:
        """POST /bundles/register returns 201 Created."""
        app.state.bundle_registry = SimpleNamespace(register=lambda bundles: None)
        resp = client.post(
            "/bundles/register",
            json={"name": "my-bundle", "uri": "git+https://example.com/my-bundle"},
        )
        assert resp.status_code == 201

    def test_register_bundle_calls_registry_register(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/register calls registry.register with name/uri."""
        captured: dict[str, str] = {}

        def fake_register(bundles: dict[str, str]) -> None:
            captured.update(bundles)

        app.state.bundle_registry = SimpleNamespace(register=fake_register)
        client.post(
            "/bundles/register",
            json={"name": "test-bundle", "uri": "git+https://example.com/test"},
        )
        assert captured == {"test-bundle": "git+https://example.com/test"}

    def test_register_bundle_returns_summary_with_name_and_uri(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/register returns BundleSummary with name and uri."""
        app.state.bundle_registry = SimpleNamespace(register=lambda bundles: None)
        resp = client.post(
            "/bundles/register",
            json={"name": "my-bundle", "uri": "git+https://example.com/my-bundle"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "my-bundle"
        assert data["uri"] == "git+https://example.com/my-bundle"


# -- DELETE /bundles/{name} --


@pytest.mark.unit
class TestDeleteBundleEndpoint:
    """Tests for DELETE /bundles/{name}."""

    def test_delete_bundle_returns_204_when_found(self, client: TestClient, app: FastAPI) -> None:
        """DELETE /bundles/{name} returns 204 when bundle exists."""
        app.state.bundle_registry = SimpleNamespace(unregister=lambda name: True)
        resp = client.delete("/bundles/test-bundle")
        assert resp.status_code == 204

    def test_delete_bundle_returns_404_when_not_found(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """DELETE /bundles/{name} returns 404 with RFC 7807 body when not registered."""
        app.state.bundle_registry = SimpleNamespace(unregister=lambda name: False)
        resp = client.delete("/bundles/nonexistent-bundle")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/bundle-not-found"


# -- POST /bundles/load --


@pytest.mark.unit
class TestLoadBundleEndpoint:
    """Tests for POST /bundles/load."""

    def test_load_bundle_returns_200_with_bundle_detail(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/load returns 200 with BundleDetail on success."""
        fake_bundle = _make_fake_bundle("loaded-bundle")

        async def fake_load(source: str) -> SimpleNamespace:
            return fake_bundle

        app.state.bundle_registry = SimpleNamespace(load=fake_load)
        resp = client.post(
            "/bundles/load",
            json={"source": "git+https://example.com/test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "loaded-bundle"

    def test_load_bundle_returns_error_on_failure(self, client: TestClient, app: FastAPI) -> None:
        """POST /bundles/load returns an error status when load raises."""

        async def fake_load(source: str) -> None:
            raise RuntimeError("Bundle load failed")

        app.state.bundle_registry = SimpleNamespace(load=fake_load)
        resp = client.post(
            "/bundles/load",
            json={"source": "git+https://example.com/bad"},
        )
        assert resp.status_code >= 400


# -- POST /bundles/prepare --


@pytest.mark.unit
class TestPrepareBundleEndpoint:
    """Tests for POST /bundles/prepare."""

    def test_prepare_bundle_returns_200_with_bundle_detail(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/prepare returns 200 with BundleDetail on success."""
        fake_bundle = _make_fake_bundle("prepare-bundle")

        async def fake_load(source: str) -> SimpleNamespace:
            return fake_bundle

        app.state.bundle_registry = SimpleNamespace(load=fake_load)
        resp = client.post(
            "/bundles/prepare",
            json={"source": "git+https://example.com/test", "install_deps": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "prepare-bundle"

    def test_prepare_bundle_uses_install_deps_flag(self, client: TestClient, app: FastAPI) -> None:
        """POST /bundles/prepare passes install_deps to bundle.prepare()."""
        received_deps: list[bool] = []

        async def fake_prepare(install_deps: bool = True) -> SimpleNamespace:
            received_deps.append(install_deps)
            return SimpleNamespace()

        fake_bundle = _make_fake_bundle("dep-bundle")
        fake_bundle.prepare = fake_prepare

        async def fake_load(source: str) -> SimpleNamespace:
            return fake_bundle

        app.state.bundle_registry = SimpleNamespace(load=fake_load)
        client.post(
            "/bundles/prepare",
            json={"source": "git+https://example.com/test", "install_deps": False},
        )
        assert received_deps == [False]


# -- POST /bundles/compose --


@pytest.mark.unit
class TestComposeBundlesEndpoint:
    """Tests for POST /bundles/compose."""

    def test_compose_bundles_returns_200_with_bundle_detail(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/compose returns 200 with composed BundleDetail."""
        bundle_b = SimpleNamespace(
            name="bundle-b",
            version="1.0",
            description="B",
            includes=[],
            providers=[],
            tools=[],
            hooks=[],
            agents={},
            context={},
        )
        bundle_a = SimpleNamespace(
            name="bundle-a",
            version="1.0",
            description="A",
            includes=[],
            providers=[],
            tools=[],
            hooks=[],
            agents={},
            context={},
            compose=lambda *args: bundle_b,
        )
        bundles_map = {"bundle-a": bundle_a, "bundle-b": bundle_b}

        async def fake_load(source: str) -> SimpleNamespace:
            return bundles_map[source]

        app.state.bundle_registry = SimpleNamespace(load=fake_load)
        resp = client.post(
            "/bundles/compose",
            json={"bundles": ["bundle-a", "bundle-b"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data

    def test_compose_bundles_returns_400_when_empty_list(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/compose returns 400 when bundles list is empty."""
        app.state.bundle_registry = SimpleNamespace(load=None)
        resp = client.post("/bundles/compose", json={"bundles": []})
        assert resp.status_code == 400


# -- POST /bundles/{name}/check-updates --


@pytest.mark.unit
class TestCheckUpdatesEndpoint:
    """Tests for POST /bundles/{name}/check-updates."""

    def test_check_updates_returns_200_with_update_info(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/{name}/check-updates returns 200 with BundleUpdateCheck."""
        fake_update_info = SimpleNamespace(
            name="foundation",
            current_version="1.0.0",
            available_version="1.1.0",
            uri="git+https://example.com",
        )
        fake_state = SimpleNamespace(
            uri="git+https://example.com",
            name="foundation",
            version="1.0.0",
            loaded_at=None,
        )

        async def fake_check_update(name: str) -> SimpleNamespace:
            return fake_update_info

        app.state.bundle_registry = SimpleNamespace(
            get_state=lambda name=None: fake_state,
            check_update=fake_check_update,
        )
        resp = client.post("/bundles/foundation/check-updates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "foundation"
        assert "has_update" in data
        assert data["has_update"] is True

    def test_check_updates_returns_no_update_when_up_to_date(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/{name}/check-updates returns has_update=False when up to date."""
        fake_state = SimpleNamespace(
            uri="git+https://example.com",
            name="foundation",
            version="1.0.0",
            loaded_at=None,
        )

        async def fake_check_update(name: str) -> None:
            return None

        app.state.bundle_registry = SimpleNamespace(
            get_state=lambda name=None: fake_state,
            check_update=fake_check_update,
        )
        resp = client.post("/bundles/foundation/check-updates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_update"] is False

    def test_check_updates_returns_404_when_bundle_not_registered(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/{name}/check-updates returns 404 when bundle not registered."""
        app.state.bundle_registry = SimpleNamespace(
            get_state=lambda name=None: None,
        )
        resp = client.post("/bundles/nonexistent/check-updates")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/bundle-not-found"


# -- POST /bundles/{name}/update --


@pytest.mark.unit
class TestUpdateBundleEndpoint:
    """Tests for POST /bundles/{name}/update."""

    def test_update_bundle_returns_200_with_bundle_detail(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/{name}/update returns 200 with BundleDetail after update."""
        fake_bundle = _make_fake_bundle("foundation")
        fake_state = SimpleNamespace(uri="git+https://example.com", name="foundation")

        async def fake_update(name: str) -> SimpleNamespace:
            return fake_bundle

        app.state.bundle_registry = SimpleNamespace(
            get_state=lambda name=None: fake_state,
            update=fake_update,
        )
        resp = client.post("/bundles/foundation/update")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "foundation"

    def test_update_bundle_returns_404_when_not_registered(
        self, client: TestClient, app: FastAPI
    ) -> None:
        """POST /bundles/{name}/update returns 404 when bundle not registered."""
        app.state.bundle_registry = SimpleNamespace(
            get_state=lambda name=None: None,
        )
        resp = client.post("/bundles/nonexistent/update")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["type"] == "https://amplifier.dev/errors/bundle-not-found"


# -- Router registration --


@pytest.mark.unit
class TestBundlesRouterRegistration:
    """Tests that all bundle routes are registered in app.py."""

    def test_list_bundles_route_registered(self) -> None:
        """GET /bundles route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/bundles" in route_paths

    def test_register_bundle_route_registered(self) -> None:
        """POST /bundles/register route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/bundles/register" in route_paths

    def test_delete_bundle_route_registered(self) -> None:
        """DELETE /bundles/{name} route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/bundles/{name}" in route_paths

    def test_load_bundle_route_registered(self) -> None:
        """POST /bundles/load route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/bundles/load" in route_paths

    def test_prepare_bundle_route_registered(self) -> None:
        """POST /bundles/prepare route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/bundles/prepare" in route_paths

    def test_compose_bundles_route_registered(self) -> None:
        """POST /bundles/compose route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/bundles/compose" in route_paths

    def test_check_updates_route_registered(self) -> None:
        """POST /bundles/{name}/check-updates route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/bundles/{name}/check-updates" in route_paths

    def test_update_bundle_route_registered(self) -> None:
        """POST /bundles/{name}/update route is registered."""
        app = create_app()
        route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
        assert "/bundles/{name}/update" in route_paths
