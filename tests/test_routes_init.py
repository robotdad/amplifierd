"""Tests for centralized router registration in routes/__init__.py."""

from __future__ import annotations

import pytest
from fastapi import APIRouter


@pytest.mark.unit
class TestAllRouters:
    """Verify ALL_ROUTERS exports all routers from routes/__init__.py."""

    def test_all_routers_exists(self):
        from amplifierd.routes import ALL_ROUTERS

        assert ALL_ROUTERS is not None

    def test_all_routers_is_list(self):
        from amplifierd.routes import ALL_ROUTERS

        assert isinstance(ALL_ROUTERS, list)

    def test_all_routers_has_ten_entries(self):
        from amplifierd.routes import ALL_ROUTERS

        assert len(ALL_ROUTERS) == 10

    def test_all_routers_are_api_routers(self):
        from amplifierd.routes import ALL_ROUTERS

        for r in ALL_ROUTERS:
            assert isinstance(r, APIRouter), f"{r!r} is not an APIRouter"

    def test_all_routers_contains_health_router(self):
        from amplifierd.routes import ALL_ROUTERS
        from amplifierd.routes.health import health_router

        assert health_router in ALL_ROUTERS

    def test_all_routers_contains_sessions_router(self):
        from amplifierd.routes import ALL_ROUTERS
        from amplifierd.routes.sessions import sessions_router

        assert sessions_router in ALL_ROUTERS

    def test_all_routers_contains_events_router(self):
        from amplifierd.routes import ALL_ROUTERS
        from amplifierd.routes.events import events_router

        assert events_router in ALL_ROUTERS

    def test_all_routers_contains_approvals_router(self):
        from amplifierd.routes import ALL_ROUTERS
        from amplifierd.routes.approvals import approvals_router

        assert approvals_router in ALL_ROUTERS

    def test_all_routers_contains_agents_router(self):
        from amplifierd.routes import ALL_ROUTERS
        from amplifierd.routes.agents import agents_router

        assert agents_router in ALL_ROUTERS

    def test_all_routers_contains_bundles_router(self):
        from amplifierd.routes import ALL_ROUTERS
        from amplifierd.routes.bundles import bundles_router

        assert bundles_router in ALL_ROUTERS

    def test_all_routers_contains_context_router(self):
        from amplifierd.routes import ALL_ROUTERS
        from amplifierd.routes.context import context_router

        assert context_router in ALL_ROUTERS

    def test_all_routers_contains_modules_router(self):
        from amplifierd.routes import ALL_ROUTERS
        from amplifierd.routes.modules import modules_router

        assert modules_router in ALL_ROUTERS

    def test_all_routers_contains_validation_router(self):
        from amplifierd.routes import ALL_ROUTERS
        from amplifierd.routes.validation import validation_router

        assert validation_router in ALL_ROUTERS

    def test_all_routers_contains_reload_router(self):
        from amplifierd.routes import ALL_ROUTERS
        from amplifierd.routes.reload import reload_router

        assert reload_router in ALL_ROUTERS


@pytest.mark.unit
class TestAppUsesAllRouters:
    """Verify app.py registers routers via the ALL_ROUTERS loop."""

    def test_app_imports_all_routers(self):
        """app module must import ALL_ROUTERS from amplifierd.routes."""
        import inspect

        import amplifierd.app as app_mod

        src = inspect.getsource(app_mod)
        assert "ALL_ROUTERS" in src, "app.py should reference ALL_ROUTERS"

    def test_create_app_includes_all_routes(self):
        """create_app() must register routes from every router in ALL_ROUTERS."""
        from amplifierd.app import create_app
        from amplifierd.routes import ALL_ROUTERS

        app = create_app()
        registered_prefixes_and_tags: set[str] = set()
        for route in app.routes:
            registered_prefixes_and_tags.add(getattr(route, "path", ""))

        # Every router's routes should appear in the app
        for router in ALL_ROUTERS:
            for route in router.routes:
                path = getattr(route, "path", "")
                assert path in registered_prefixes_and_tags, (
                    f"Route {path!r} from {router!r} not found in app routes"
                )
