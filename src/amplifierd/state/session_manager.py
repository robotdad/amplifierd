"""SessionManager — central registry of all live sessions.

The SessionManager is the only component that creates, stores, or destroys
SessionHandle instances. All route handlers access sessions through it.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from amplifierd.config import DaemonSettings
from amplifierd.state.event_bus import EventBus
from amplifierd.state.session_handle import SessionHandle
from amplifierd.state.session_index import SessionIndex, SessionIndexEntry

logger = logging.getLogger(__name__)


class SessionManager:
    """Central owner of all live sessions.

    A single instance is created at startup and stored in app.state.
    """

    def __init__(
        self,
        *,
        event_bus: EventBus,
        settings: DaemonSettings,
        bundle_registry: Any = None,
        sessions_dir: Path | None = None,
    ) -> None:
        self._sessions: dict[str, SessionHandle] = {}
        self._event_bus = event_bus
        self._settings = settings
        self._bundle_registry = bundle_registry
        self._sessions_dir = sessions_dir
        self._index: SessionIndex | None = None
        if sessions_dir:
            index_path = sessions_dir / "index.json"
            if index_path.exists():
                try:
                    self._index = SessionIndex.load(index_path)
                except Exception:
                    self._index = SessionIndex.rebuild(sessions_dir)
            else:
                self._index = SessionIndex.rebuild(sessions_dir)

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def settings(self) -> DaemonSettings:
        return self._settings

    @property
    def sessions_dir(self) -> Path | None:
        return self._sessions_dir

    def resolve_working_dir(self, request_working_dir: str | None) -> str:
        """Resolve working directory using the fallback chain:
        request > daemon config > user home.

        Tilde (``~``) prefixes are expanded to the user's home directory
        so the stored path is always absolute.
        """
        import os

        if request_working_dir:
            return os.path.expanduser(request_working_dir)
        if self._settings.default_working_dir:
            return str(self._settings.default_working_dir)
        return str(Path.home())

    def register(
        self,
        *,
        session: Any,  # AmplifierSession
        prepared_bundle: Any | None,  # PreparedBundle
        bundle_name: str,
        working_dir: str | None = None,
    ) -> SessionHandle:
        """Register a pre-created session and wrap it in a SessionHandle."""
        session_id: str = session.session_id
        if session_id in self._sessions:
            msg = f"Session {session_id} already exists"
            raise ValueError(msg)

        handle = SessionHandle(
            session=session,
            prepared_bundle=prepared_bundle,
            bundle_name=bundle_name,
            event_bus=self._event_bus,
            working_dir=working_dir,
        )
        self._sessions[session_id] = handle
        if self._index is not None:
            self._index.add(
                SessionIndexEntry(
                    session_id=session_id,
                    status=str(handle.status),
                    bundle=bundle_name,
                    created_at=handle.created_at.isoformat(),
                    last_activity=handle.last_activity.isoformat(),
                    parent_session_id=getattr(session, "parent_id", None),
                )
            )
            self._index.save()
        logger.info("Registered session %s (bundle=%s)", session_id, bundle_name)
        return handle

    def get(self, session_id: str) -> SessionHandle | None:
        """Get a session by ID, or None if not found."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        """List all sessions: active in-memory sessions first, then historical from index.

        Returns a list of dicts with a consistent shape:
            session_id, status, bundle, created_at, last_activity,
            parent_session_id, stale, is_active, working_dir
        """
        active_ids = set(self._sessions)
        result: list[dict] = []

        for handle in self._sessions.values():
            result.append(
                {
                    "session_id": handle.session_id,
                    "status": str(handle.status),
                    "bundle": handle.bundle_name,
                    "created_at": handle.created_at.isoformat(),
                    "last_activity": handle.last_activity.isoformat(),
                    "parent_session_id": handle.parent_id,
                    "stale": handle.stale,
                    "is_active": True,
                    "working_dir": handle.working_dir,
                }
            )

        if self._index is not None:
            for entry in self._index.list_entries():
                if entry.session_id not in active_ids:
                    result.append(
                        {
                            "session_id": entry.session_id,
                            "status": entry.status,
                            "bundle": entry.bundle,
                            "created_at": entry.created_at,
                            "last_activity": entry.last_activity,
                            "parent_session_id": entry.parent_session_id,
                            "stale": None,
                            "is_active": False,
                            "working_dir": None,
                        }
                    )

        return result

    async def create(
        self,
        *,
        bundle_name: str | None = None,
        bundle_uri: str | None = None,
        working_dir: str | None = None,
    ) -> SessionHandle:
        """Create a new session by loading and preparing a bundle.

        Args:
            bundle_name: Registered bundle name to load.
            bundle_uri: Bundle URI to load directly.
            working_dir: Working directory override; falls back to daemon config or home.

        Returns:
            The newly created and registered SessionHandle.

        Raises:
            RuntimeError: If BundleRegistry is not available.
            ValueError: If neither bundle_name nor bundle_uri is provided.
        """
        if not self._bundle_registry:
            raise RuntimeError("BundleRegistry not available")
        if not bundle_name and not bundle_uri:
            raise ValueError("bundle_name or bundle_uri required")

        wd = self.resolve_working_dir(working_dir)
        name_or_uri = bundle_uri or bundle_name
        bundle = await self._bundle_registry.load(name_or_uri)

        # Inject providers from ~/.amplifier/settings.yaml BEFORE prepare()
        # so the activation step downloads and installs their dependencies.
        from amplifierd.providers import inject_providers, load_provider_config

        providers = load_provider_config()
        inject_providers(bundle, providers)

        prepared = await bundle.prepare()
        session = await prepared.create_session()

        # Register transcript/metadata persistence hooks
        if self._sessions_dir:
            from amplifierd.persistence import register_persistence_hooks

            session_dir = self._sessions_dir / session.session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            info_path = session_dir / "session-info.json"
            if not info_path.exists():
                info_path.write_text(json.dumps({"working_dir": str(wd)}))
            register_persistence_hooks(
                session,
                session_dir,
                initial_metadata={
                    "session_id": session.session_id,
                    "created": datetime.now(tz=UTC).isoformat(),
                    "bundle": bundle_name or bundle_uri or "unknown",
                    "working_dir": str(wd),
                },
            )

        # Register spawn capability so delegate tool can spawn sub-sessions
        try:
            from amplifierd.spawn import register_spawn_capability

            register_spawn_capability(session, prepared, session.session_id)
        except (ImportError, Exception):  # noqa: BLE001
            logger.debug("Spawn capability registration skipped", exc_info=True)

        handle = self.register(
            session=session,
            prepared_bundle=prepared,
            bundle_name=bundle_name or bundle_uri or "unknown",
            working_dir=wd,
        )
        return handle

    async def resume(self, session_id: str) -> SessionHandle:
        """Resume a session from disk after server restart.

        Loads the transcript from ``{sessions_dir}/{session_id}/transcript.jsonl``,
        handles orphaned tool calls, creates a fresh session with
        ``is_resumed=True``, and injects the transcript into the new
        session's context.

        Args:
            session_id: ID of the session to resume.

        Returns:
            The resumed SessionHandle.

        Raises:
            ValueError: If sessions_dir is not configured.
            RuntimeError: If BundleRegistry is not available.
            FileNotFoundError: If session directory or transcript not found.
        """
        # Return existing handle if already active
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing

        if not self._sessions_dir:
            raise ValueError("Session persistence not configured (sessions_dir is None)")
        if not self._bundle_registry:
            raise RuntimeError("BundleRegistry not available")

        session_dir = self._sessions_dir / session_id
        if not session_dir.exists():
            raise FileNotFoundError(f"No session directory for {session_id}")

        # 1. Load transcript from disk (offload sync I/O to thread)
        from amplifierd.persistence import load_metadata, load_transcript

        transcript = await asyncio.to_thread(load_transcript, session_dir)

        # 2. Handle orphaned tool calls
        try:
            from amplifier_foundation.session import (
                add_synthetic_tool_results,
                find_orphaned_tool_calls,
            )

            orphan_ids = find_orphaned_tool_calls(transcript)
            if orphan_ids:
                transcript = add_synthetic_tool_results(transcript, orphan_ids)
                logger.info(
                    "Added synthetic results for %d orphaned tool calls in %s",
                    len(orphan_ids),
                    session_id,
                )
        except ImportError:
            logger.warning(
                "amplifier_foundation.session helpers not available; "
                "skipping orphan handling"
            )

        # 3. Load metadata to determine bundle and working_dir
        metadata = await asyncio.to_thread(load_metadata, session_dir)
        bundle_name = metadata.get("bundle", self._settings.default_bundle or "unknown")
        working_dir = metadata.get("working_dir", str(Path.home()))

        # 4. Load bundle, inject providers, prepare, create session
        bundle = await self._bundle_registry.load(bundle_name)

        from amplifierd.providers import inject_providers, load_provider_config

        providers = load_provider_config()
        inject_providers(bundle, providers)

        prepared = await bundle.prepare()
        session = await prepared.create_session(
            session_id=session_id,
            is_resumed=True,
        )

        # 5. Inject transcript into context (preserving system prompt)
        context = session.coordinator.get("context")
        if context and hasattr(context, "set_messages"):
            current_msgs = await context.get_messages()
            system_msgs = [m for m in current_msgs if m.get("role") == "system"]

            await context.set_messages(transcript)

            # Re-inject system prompt if transcript lacks one
            restored = await context.get_messages()
            if system_msgs and not any(
                m.get("role") == "system" for m in restored
            ):
                await context.set_messages(system_msgs + list(restored))

        # 6. Register persistence hooks
        from amplifierd.persistence import register_persistence_hooks

        register_persistence_hooks(session, session_dir)

        # 7. Register spawn capability
        try:
            from amplifierd.spawn import register_spawn_capability

            register_spawn_capability(session, prepared, session_id)
        except (ImportError, Exception):  # noqa: BLE001
            logger.debug("Spawn capability registration skipped", exc_info=True)

        # 8. Register in SessionManager
        handle = self.register(
            session=session,
            prepared_bundle=prepared,
            bundle_name=bundle_name,
            working_dir=working_dir,
        )
        logger.info(
            "Session %s resumed (%d messages restored)",
            session_id,
            len(transcript),
        )
        return handle

    async def destroy(self, session_id: str) -> None:
        """Destroy a session: cleanup resources and remove from registry."""
        handle = self._sessions.pop(session_id, None)
        if handle is None:
            logger.warning("Attempted to destroy unknown session %s", session_id)
            return
        await handle.cleanup()
        if self._index is not None:
            self._index.update(session_id, status="completed")
            self._index.save()
        logger.info("Destroyed session %s", session_id)

    async def shutdown(self) -> None:
        """Gracefully shutdown all sessions (called on daemon shutdown)."""
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            try:
                await self.destroy(sid)
            except Exception as exc:
                logger.warning("Error destroying session %s during shutdown: %s", sid, exc)
