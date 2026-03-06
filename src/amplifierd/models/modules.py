"""Module request/response models."""

from typing import Any

from pydantic import BaseModel


class MountModuleRequest(BaseModel):
    """Request to mount a module."""

    module_id: str
    config: dict[str, Any] | None = None
    source: str | None = None


class UnmountModuleRequest(BaseModel):
    """Request to unmount a module."""

    mount_point: str | None = None
    name: str | None = None


class ModuleSummary(BaseModel):
    """Summary of a mounted module."""

    id: str
    name: str
    version: str | None = None
    type: str | None = None
    mount_point: str | None = None
    description: str | None = None


class ModuleListResponse(BaseModel):
    """Response listing modules."""

    modules: list[ModuleSummary]


class ValidateMountPlanRequest(BaseModel):
    """Request to validate a mount plan."""

    mount_plan: dict[str, Any]


class ValidateModuleRequest(BaseModel):
    """Request to validate a module."""

    module_id: str
    type: str | None = None
    source: str | None = None
    config: dict[str, Any] | None = None


class ValidateBundleRequest(BaseModel):
    """Request to validate a bundle source."""

    source: str


class ValidationResponse(BaseModel):
    """Response from a validation operation."""

    valid: bool
    errors: list[str] | None = None
    warnings: list[str] | None = None
    checks: list[Any] | None = None
