"""Tests for provider configuration loading and injection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.mark.unit
class TestLoadProviderConfig:
    """Tests for load_provider_config()."""

    def test_missing_file(self, tmp_path: Path) -> None:
        from amplifierd.providers import load_provider_config

        result = load_provider_config(home=tmp_path)
        assert result == []

    def test_no_providers_key(self, tmp_path: Path) -> None:
        from amplifierd.providers import load_provider_config

        (tmp_path / "settings.yaml").write_text("config:\n  other: true\n")
        result = load_provider_config(home=tmp_path)
        assert result == []

    def test_empty_config(self, tmp_path: Path) -> None:
        from amplifierd.providers import load_provider_config

        (tmp_path / "settings.yaml").write_text("")
        result = load_provider_config(home=tmp_path)
        assert result == []

    def test_reads_providers(self, tmp_path: Path) -> None:
        from amplifierd.providers import load_provider_config

        (tmp_path / "settings.yaml").write_text(
            "config:\n"
            "  providers:\n"
            "  - module: provider-anthropic\n"
            "    source: git+https://example.com/provider\n"
            "    config:\n"
            "      api_key: sk-test\n"
            "      default_model: claude-opus-4-6\n"
        )
        result = load_provider_config(home=tmp_path)
        assert len(result) == 1
        assert result[0]["module"] == "provider-anthropic"
        assert result[0]["config"]["api_key"] == "sk-test"

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        from amplifierd.providers import load_provider_config

        (tmp_path / "settings.yaml").write_text("{{invalid yaml!!")
        result = load_provider_config(home=tmp_path)
        assert result == []

    def test_providers_not_a_list(self, tmp_path: Path) -> None:
        from amplifierd.providers import load_provider_config

        (tmp_path / "settings.yaml").write_text("config:\n  providers: not-a-list\n")
        result = load_provider_config(home=tmp_path)
        assert result == []


@pytest.mark.unit
class TestExpandEnvVars:
    """Tests for expand_env_vars()."""

    def test_string_expansion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from amplifierd.providers import expand_env_vars

        monkeypatch.setenv("TEST_KEY", "my-secret")
        assert expand_env_vars("${TEST_KEY}") == "my-secret"

    def test_default_value(self) -> None:
        from amplifierd.providers import expand_env_vars

        result = expand_env_vars("${DEFINITELY_NOT_SET:fallback}")
        assert result == "fallback"

    def test_missing_no_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from amplifierd.providers import expand_env_vars

        monkeypatch.delenv("DEFINITELY_NOT_SET", raising=False)
        assert expand_env_vars("${DEFINITELY_NOT_SET}") == ""

    def test_nested_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from amplifierd.providers import expand_env_vars

        monkeypatch.setenv("MY_KEY", "secret123")
        result = expand_env_vars({"config": {"api_key": "${MY_KEY}", "model": "gpt-4"}})
        assert result == {"config": {"api_key": "secret123", "model": "gpt-4"}}

    def test_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from amplifierd.providers import expand_env_vars

        monkeypatch.setenv("A", "1")
        monkeypatch.setenv("B", "2")
        assert expand_env_vars(["${A}", "${B}", "literal"]) == ["1", "2", "literal"]

    def test_empty_env_var_stripped_from_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from amplifierd.providers import expand_env_vars

        monkeypatch.setenv("GOOD_KEY", "value")
        monkeypatch.setenv("EMPTY_KEY", "")
        monkeypatch.delenv("MISSING_KEY", raising=False)
        result = expand_env_vars({
            "good": "${GOOD_KEY}",
            "empty": "${EMPTY_KEY}",
            "missing": "${MISSING_KEY}",
            "literal": "keep",
        })
        assert result == {"good": "value", "literal": "keep"}

    def test_non_string_passthrough(self) -> None:
        from amplifierd.providers import expand_env_vars

        assert expand_env_vars(42) == 42
        assert expand_env_vars(True) is True
        assert expand_env_vars(None) is None


def _make_bundle(
    providers: list[dict[str, Any]] | None = None,
) -> SimpleNamespace:
    """Create a fake Bundle for testing."""
    return SimpleNamespace(providers=list(providers or []))


@pytest.mark.unit
class TestInjectProviders:
    """Tests for inject_providers()."""

    def test_sets_providers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from amplifierd.providers import inject_providers

        monkeypatch.setenv("KEY", "val")
        bundle = _make_bundle()
        providers = [{"module": "provider-test", "config": {"api_key": "${KEY}"}}]
        inject_providers(bundle, providers)
        assert len(bundle.providers) == 1
        assert bundle.providers[0]["config"]["api_key"] == "val"

    def test_empty_noop(self) -> None:
        from amplifierd.providers import inject_providers

        bundle = _make_bundle()
        inject_providers(bundle, [])
        assert bundle.providers == []

    def test_merges_with_existing(self) -> None:
        from amplifierd.providers import inject_providers

        bundle = _make_bundle(
            providers=[
                {"module": "existing-provider", "config": {"key": "old"}},
            ]
        )
        providers = [
            {"module": "existing-provider", "config": {"key": "new"}},
            {"module": "new-provider", "config": {"key": "added"}},
        ]
        inject_providers(bundle, providers)
        assert len(bundle.providers) == 2
        by_module = {p["module"]: p for p in bundle.providers}
        assert by_module["existing-provider"]["config"]["key"] == "new"
        assert by_module["new-provider"]["config"]["key"] == "added"


@pytest.mark.unit
class TestMergeSettingsProviders:
    """Tests for merge_settings_providers()."""

    def test_empty_settings(self) -> None:
        from amplifierd.providers import merge_settings_providers

        existing = [{"module": "a", "config": {}}]
        assert merge_settings_providers(existing, []) == existing

    def test_settings_override(self) -> None:
        from amplifierd.providers import merge_settings_providers

        existing = [{"module": "a", "config": {"key": "old"}}]
        settings = [{"module": "a", "config": {"key": "new"}}]
        result = merge_settings_providers(existing, settings)
        assert len(result) == 1
        assert result[0]["config"]["key"] == "new"

    def test_adds_new_provider(self) -> None:
        from amplifierd.providers import merge_settings_providers

        existing = [{"module": "a", "config": {}}]
        settings = [{"module": "b", "config": {}}]
        result = merge_settings_providers(existing, settings)
        assert len(result) == 2
