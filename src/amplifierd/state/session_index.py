from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from dataclasses import fields as dc_fields
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SessionIndexEntry:
    session_id: str
    status: str
    bundle: str
    created_at: str
    last_activity: str
    parent_session_id: str | None = None


_ENTRY_FIELDS = {f.name for f in dc_fields(SessionIndexEntry)}


class SessionIndex:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: dict[str, SessionIndexEntry] = {}

    def add(self, entry: SessionIndexEntry) -> None:
        self._entries[entry.session_id] = entry

    def update(self, session_id: str, **fields: object) -> bool:
        unknown = set(fields) - _ENTRY_FIELDS
        if unknown:
            raise ValueError(f"Unknown SessionIndexEntry fields: {unknown}")
        if session_id not in self._entries:
            return False
        for k, v in fields.items():
            setattr(self._entries[session_id], k, v)
        return True

    def remove(self, session_id: str) -> None:
        self._entries.pop(session_id, None)

    def get(self, session_id: str) -> SessionIndexEntry | None:
        return self._entries.get(session_id)

    def list_entries(self) -> list[SessionIndexEntry]:
        return list(self._entries.values())

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        data = [asdict(e) for e in self._entries.values()]
        tmp.write_text(json.dumps(data, indent=2))
        os.rename(tmp, self._path)

    @classmethod
    def load(cls, path: Path) -> SessionIndex:
        index = cls(path)
        if not path.exists():
            return index
        try:
            data = json.loads(path.read_text())
            for item in data:
                index._entries[item["session_id"]] = SessionIndexEntry(**item)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("Session index corrupted at %s, starting empty", path)
        return index

    @classmethod
    def rebuild(cls, sessions_dir: Path) -> SessionIndex:
        index_path = sessions_dir / "index.json"
        index = cls(index_path)
        if not sessions_dir.exists():
            return index
        for sdir in sessions_dir.iterdir():
            if not sdir.is_dir():
                continue
            meta_path = sdir / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text())
                index.add(
                    SessionIndexEntry(
                        session_id=sdir.name,
                        status=meta.get("status", "completed"),
                        bundle=meta.get("bundle", "unknown"),
                        created_at=meta.get("created_at", ""),
                        last_activity=meta.get("last_activity", meta.get("created_at", "")),
                        parent_session_id=meta.get("parent_session_id"),
                    )
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                logger.warning("Skipping unreadable session dir: %s", sdir)
        return index
