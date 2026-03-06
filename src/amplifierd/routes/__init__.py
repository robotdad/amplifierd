"""FastAPI route modules — all routers registered here."""

from __future__ import annotations

from amplifierd.routes.agents import agents_router
from amplifierd.routes.approvals import approvals_router
from amplifierd.routes.bundles import bundles_router
from amplifierd.routes.context import context_router
from amplifierd.routes.events import events_router
from amplifierd.routes.health import health_router
from amplifierd.routes.modules import modules_router
from amplifierd.routes.reload import reload_router
from amplifierd.routes.sessions import sessions_router
from amplifierd.routes.validation import validation_router

ALL_ROUTERS = [
    health_router,
    sessions_router,
    events_router,
    approvals_router,
    agents_router,
    bundles_router,
    context_router,
    modules_router,
    validation_router,
    reload_router,
]
