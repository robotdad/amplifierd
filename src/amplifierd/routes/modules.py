"""Module management routes for global discovery and session-level mount/unmount."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from amplifierd.models.errors import ErrorTypeURI, ProblemDetail
from amplifierd.models.modules import (
    ModuleListResponse,
    ModuleSummary,
    MountModuleRequest,
    UnmountModuleRequest,
)
from amplifierd.state.session_handle import SessionHandle

logger = logging.getLogger(__name__)

modules_router = APIRouter(tags=["modules"])


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_handle_or_404(request: Request, session_id: str) -> SessionHandle:
    """Return SessionHandle or raise HTTPException 404 with RFC 7807 ProblemDetail body."""
    manager = request.app.state.session_manager
    handle = manager.get(session_id)
    if handle is None:
        detail = ProblemDetail(
            type=ErrorTypeURI.SESSION_NOT_FOUND,
            title="Session Not Found",
            status=404,
            detail=f"Session '{session_id}' not found",
            instance=str(request.url.path),
        )
        raise HTTPException(
            status_code=404,
            detail=detail.model_dump(exclude_none=True),
        )
    return handle


def _module_to_summary(mod: Any) -> ModuleSummary:
    """Convert a module object (or duck-typed namespace) to ModuleSummary."""
    return ModuleSummary(
        id=str(getattr(mod, "id", "")),
        name=str(getattr(mod, "name", "")),
        version=getattr(mod, "version", None) or None,
        type=getattr(mod, "type", None) or None,
        mount_point=getattr(mod, "mount_point", None) or None,
        description=getattr(mod, "description", None) or None,
    )


def _coordinator_unavailable_error(path: str) -> HTTPException:
    """Return a 503 HTTPException when the session coordinator lacks the needed method."""
    detail = ProblemDetail(
        type=ErrorTypeURI.CONFIGURATION_ERROR,
        title="Module Coordinator Unavailable",
        status=503,
        detail="Module coordinator is not available for this session",
        instance=path,
    )
    return HTTPException(
        status_code=503,
        detail=detail.model_dump(exclude_none=True),
    )


# ------------------------------------------------------------------
# Global module discovery endpoints
# ------------------------------------------------------------------


@modules_router.get("/modules", response_model=ModuleListResponse)
async def list_modules(request: Request) -> ModuleListResponse:
    """Discover all available modules from the global module coordinator."""
    coordinator = getattr(request.app.state, "module_coordinator", None)

    if coordinator is None:
        return ModuleListResponse(modules=[])

    try:
        raw = coordinator.list_available()
        return ModuleListResponse(modules=[_module_to_summary(m) for m in raw])
    except Exception:
        logger.warning("Failed to list available modules from coordinator", exc_info=True)
        return ModuleListResponse(modules=[])


@modules_router.get("/modules/{module_id}", response_model=ModuleSummary)
async def get_module(request: Request, module_id: str) -> ModuleSummary:
    """Get details for a specific module by ID."""
    coordinator = getattr(request.app.state, "module_coordinator", None)

    if coordinator is None:
        detail = ProblemDetail(
            type=ErrorTypeURI.MODULE_NOT_FOUND,
            title="Module Not Found",
            status=404,
            detail=f"Module '{module_id}' not found",
            instance=str(request.url.path),
        )
        raise HTTPException(
            status_code=404,
            detail=detail.model_dump(exclude_none=True),
        )

    try:
        mod = coordinator.get_module(module_id)
    except Exception:
        logger.warning("Failed to get module '%s' from coordinator", module_id, exc_info=True)
        mod = None

    if mod is None:
        detail = ProblemDetail(
            type=ErrorTypeURI.MODULE_NOT_FOUND,
            title="Module Not Found",
            status=404,
            detail=f"Module '{module_id}' not found",
            instance=str(request.url.path),
        )
        raise HTTPException(
            status_code=404,
            detail=detail.model_dump(exclude_none=True),
        )

    return _module_to_summary(mod)


# ------------------------------------------------------------------
# Session-level module endpoints
# ------------------------------------------------------------------


@modules_router.post("/sessions/{session_id}/modules/mount", response_model=ModuleSummary)
async def mount_module(
    request: Request, session_id: str, body: MountModuleRequest
) -> ModuleSummary:
    """Hot-mount a module into a live session."""
    handle = _get_handle_or_404(request, session_id)
    coordinator = handle.session.coordinator

    if not callable(getattr(coordinator, "mount", None)):
        raise _coordinator_unavailable_error(str(request.url.path))

    try:
        mod = coordinator.mount(body.module_id, config=body.config, source=body.source)
    except Exception as exc:
        logger.exception("Failed to mount module '%s' in session %s", body.module_id, session_id)
        detail = ProblemDetail(
            type=ErrorTypeURI.MODULE_ACTIVATION_ERROR,
            title="Module Mount Failed",
            status=500,
            detail=f"Failed to mount module '{body.module_id}': {exc}",
            instance=str(request.url.path),
        )
        raise HTTPException(
            status_code=500,
            detail=detail.model_dump(exclude_none=True),
        )

    return _module_to_summary(mod)


@modules_router.post("/sessions/{session_id}/modules/unmount", status_code=204)
async def unmount_module(request: Request, session_id: str, body: UnmountModuleRequest) -> None:
    """Unmount a module from a live session."""
    handle = _get_handle_or_404(request, session_id)
    coordinator = handle.session.coordinator

    if not callable(getattr(coordinator, "unmount", None)):
        raise _coordinator_unavailable_error(str(request.url.path))

    try:
        coordinator.unmount(name=body.name, mount_point=body.mount_point)
    except Exception as exc:
        logger.exception("Failed to unmount module from session %s", session_id)
        detail = ProblemDetail(
            type=ErrorTypeURI.MODULE_ACTIVATION_ERROR,
            title="Module Unmount Failed",
            status=500,
            detail=f"Failed to unmount module: {exc}",
            instance=str(request.url.path),
        )
        raise HTTPException(
            status_code=500,
            detail=detail.model_dump(exclude_none=True),
        )


@modules_router.get("/sessions/{session_id}/modules", response_model=ModuleListResponse)
async def list_session_modules(request: Request, session_id: str) -> ModuleListResponse:
    """List all modules mounted in a session."""
    handle = _get_handle_or_404(request, session_id)
    coordinator = handle.session.coordinator

    if not callable(getattr(coordinator, "list_mounted", None)):
        return ModuleListResponse(modules=[])

    try:
        raw = coordinator.list_mounted()
        return ModuleListResponse(modules=[_module_to_summary(m) for m in raw])
    except Exception:
        logger.warning("Failed to list mounted modules for session %s", session_id, exc_info=True)
        return ModuleListResponse(modules=[])
