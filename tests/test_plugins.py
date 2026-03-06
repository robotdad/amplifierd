"""Tests for plugin discovery system."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi import APIRouter

from amplifierd.plugins import discover_plugins


@pytest.mark.unit
class TestDiscoverPlugins:
    """Tests for discover_plugins with entry point-based plugin loading."""

    def test_no_plugins_installed(self):
        """When no entry points exist, discover_plugins returns an empty list."""
        with patch("amplifierd.plugins._get_entry_points", return_value=[]):
            result = discover_plugins(disabled=[])

        assert result == []

    def test_disabled_plugin_skipped(self):
        """Disabled plugins are skipped without calling load()."""
        ep = MagicMock()
        ep.name = "myplugin"

        with patch("amplifierd.plugins._get_entry_points", return_value=[ep]):
            result = discover_plugins(disabled=["myplugin"])

        assert result == []
        ep.load.assert_not_called()

    def test_broken_plugin_does_not_crash(self):
        """A broken plugin is skipped; good plugins still load. Result has 1 item."""
        # Broken plugin: load() raises an exception
        broken_ep = MagicMock()
        broken_ep.name = "broken"
        broken_ep.load.side_effect = Exception("boom")

        # Good plugin: load() returns a module with create_router that returns APIRouter
        good_router = APIRouter()
        good_module = MagicMock()
        good_module.create_router.return_value = good_router

        good_ep = MagicMock()
        good_ep.name = "good"
        good_ep.load.return_value = good_module

        with patch("amplifierd.plugins._get_entry_points", return_value=[broken_ep, good_ep]):
            result = discover_plugins(disabled=[])

        assert len(result) == 1
        assert result[0] == ("good", good_router)

    def test_non_apirouter_return_skipped(self):
        """A plugin whose create_router() returns a non-APIRouter is skipped."""
        bad_module = MagicMock()
        bad_module.create_router.return_value = "not_a_router"

        bad_ep = MagicMock()
        bad_ep.name = "bad_return"
        bad_ep.load.return_value = bad_module

        with patch("amplifierd.plugins._get_entry_points", return_value=[bad_ep]):
            result = discover_plugins(disabled=[])

        assert result == []

    def test_disabled_plugin_logs_info(self, caplog):
        """Skipping a disabled plugin emits an info log."""
        ep = MagicMock()
        ep.name = "myplugin"

        with (
            patch("amplifierd.plugins._get_entry_points", return_value=[ep]),
            caplog.at_level(logging.INFO, logger="amplifierd.plugins"),
        ):
            discover_plugins(disabled=["myplugin"])

        assert "Skipping disabled plugin: myplugin" in caplog.text

    def test_broken_plugin_logs_exception(self, caplog):
        """A broken plugin emits an exception-level log."""
        broken_ep = MagicMock()
        broken_ep.name = "broken"
        broken_ep.load.side_effect = Exception("boom")

        with (
            patch("amplifierd.plugins._get_entry_points", return_value=[broken_ep]),
            # logger.exception() emits at ERROR level
            caplog.at_level(logging.ERROR, logger="amplifierd.plugins"),
        ):
            discover_plugins(disabled=[])

        assert "Failed to load plugin: broken" in caplog.text

    def test_state_forwarded_to_create_router(self):
        """The state argument is forwarded to each plugin's create_router()."""
        router = APIRouter()
        module = MagicMock()
        module.create_router.return_value = router

        ep = MagicMock()
        ep.name = "stateful"
        ep.load.return_value = module

        sentinel = object()
        with patch("amplifierd.plugins._get_entry_points", return_value=[ep]):
            discover_plugins(disabled=[], state=sentinel)

        module.create_router.assert_called_once_with(sentinel)
