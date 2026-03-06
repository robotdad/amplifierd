"""Entry point-based plugin discovery for amplifierd."""

from __future__ import annotations

import importlib.metadata
import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "amplifierd.plugins"


def _get_entry_points() -> list[importlib.metadata.EntryPoint]:
    """Return installed entry points for the plugin group.

    Extracted as a standalone function for testability.
    """
    return list(importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP))


def discover_plugins(disabled: list[str], state: Any = None) -> list[tuple[str, APIRouter]]:
    """Discover and load plugins from entry points.

    Iterates registered entry points, skips disabled plugins, loads each
    plugin module and calls its ``create_router(state)`` factory.  Plugins
    that raise any exception are logged and skipped so one broken plugin
    cannot take down the daemon.

    Returns a list of ``(name, router)`` tuples for successfully loaded plugins.
    """
    loaded: list[tuple[str, APIRouter]] = []
    disabled_set = set(disabled)

    for ep in _get_entry_points():
        if ep.name in disabled_set:
            logger.info("Skipping disabled plugin: %s", ep.name)
            continue

        try:
            module = ep.load()
            router = module.create_router(state)
            if not isinstance(router, APIRouter):
                msg = f"Plugin {ep.name!r} create_router() did not return an APIRouter"
                raise TypeError(msg)
            loaded.append((ep.name, router))
        except Exception:
            logger.exception("Failed to load plugin: %s", ep.name)

    return loaded
