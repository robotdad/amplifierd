"""Provider configuration loading and injection.

Reads provider config from ~/.amplifier/settings.yaml (same source as amplifier-app-cli)
and injects it into PreparedBundle before session creation.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?}")


def load_provider_config(home: Path | None = None) -> list[dict[str, Any]]:
    """Load provider configuration from ~/.amplifier/settings.yaml.

    Args:
        home: Amplifier home directory. Falls back to AMPLIFIER_HOME env var,
              then ~/.amplifier.

    Returns:
        List of provider config dicts from config.providers, or empty list.
    """
    if home is None:
        home = Path(os.environ.get("AMPLIFIER_HOME", Path.home() / ".amplifier"))
    settings_path = home / "settings.yaml"
    if not settings_path.is_file():
        logger.debug("No settings file at %s", settings_path)
        return []
    try:
        data = yaml.safe_load(settings_path.read_text()) or {}
    except Exception:
        logger.warning("Failed to read %s", settings_path, exc_info=True)
        return []
    providers = data.get("config", {}).get("providers", [])
    if not isinstance(providers, list):
        return []
    logger.info(
        "Loaded %d provider(s) from %s: %s",
        len(providers),
        settings_path,
        [p.get("module", "?") for p in providers if isinstance(p, dict)],
    )
    return providers


def expand_env_vars(value: Any) -> Any:
    """Recursively expand ${VAR} and ${VAR:default} references in config values.

    After expansion, dict entries whose values are empty strings are removed.
    This prevents empty env vars (e.g. ANTHROPIC_BASE_URL='') from overriding
    provider defaults with blank values.
    """
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), m.group(2) if m.group(2) is not None else ""),
            value,
        )
    if isinstance(value, dict):
        expanded = {k: expand_env_vars(v) for k, v in value.items()}
        return {k: v for k, v in expanded.items() if v != ""}
    if isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    return value


def merge_settings_providers(
    existing: list[dict[str, Any]], settings_providers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge settings providers into an existing provider list.

    Settings override bundle providers by module ID.
    Environment variables in settings values are expanded.

    Args:
        existing: Current provider list (from bundle).
        settings_providers: Provider config list from load_provider_config().

    Returns:
        Merged provider list with env vars expanded.
    """
    if not settings_providers:
        return list(existing)
    expanded = expand_env_vars(settings_providers)
    by_module: dict[str, dict[str, Any]] = {
        p["module"]: p for p in existing if isinstance(p, dict) and "module" in p
    }
    for p in expanded:
        if isinstance(p, dict) and "module" in p:
            by_module[p["module"]] = p
    return list(by_module.values())


def inject_providers(bundle: Any, providers: list[dict[str, Any]]) -> None:
    """Inject provider config into a Bundle before prepare().

    Must be called BEFORE bundle.prepare() so that the activation step
    downloads and installs provider dependencies (e.g. the anthropic SDK).

    Args:
        bundle: An AmplifierBundle instance (has .providers list).
        providers: Provider config list from load_provider_config().
    """
    if not providers:
        return
    bundle.providers = merge_settings_providers(bundle.providers, providers)
