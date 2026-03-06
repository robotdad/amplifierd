"""Bundle request/response models."""

from typing import Any

from pydantic import BaseModel


class RegisterBundleRequest(BaseModel):
    """Request to register a bundle."""

    name: str
    uri: str


class LoadBundleRequest(BaseModel):
    """Request to load a bundle."""

    source: str


class PrepareBundleRequest(BaseModel):
    """Request to prepare a bundle."""

    source: str
    install_deps: bool | None = None


class ComposeBundlesRequest(BaseModel):
    """Request to compose multiple bundles."""

    bundles: list[str]
    overrides: dict[str, Any] | None = None


class BundleSummary(BaseModel):
    """Summary of a loaded bundle."""

    name: str
    uri: str | None = None
    version: str | None = None
    loaded_at: str | None = None
    has_updates: bool | None = None


class BundleListResponse(BaseModel):
    """Response listing bundles."""

    bundles: list[BundleSummary]


class BundleDetail(BaseModel):
    """Detailed bundle information."""

    name: str
    version: str | None = None
    description: str | None = None
    includes: list[str] | None = None
    providers: list[Any] | None = None
    tools: list[Any] | None = None
    hooks: list[Any] | None = None
    agents: dict[str, Any] | None = None
    context_files: list[str] | None = None


class BundleUpdateCheck(BaseModel):
    """Result of checking a bundle for updates."""

    name: str
    current_version: str | None = None
    available_version: str | None = None
    has_update: bool


class ReloadBundlesResponse(BaseModel):
    """Response from reloading all registered bundles."""

    reloaded: list[str]
    failed: list[str]
    total: int


class ReloadStatusResponse(BaseModel):
    """Response from checking reload/update status for all registered bundles."""

    bundles: list[BundleUpdateCheck]
