import json

import pytest

from amplifierd.state.session_index import SessionIndex, SessionIndexEntry


def test_create_and_load_index(tmp_path):
    index = SessionIndex(tmp_path / "index.json")
    entry = SessionIndexEntry(
        session_id="abc-123",
        status="idle",
        bundle="test-bundle",
        created_at="2026-03-03T10:00:00Z",
        last_activity="2026-03-03T10:00:00Z",
    )
    index.add(entry)
    index.save()
    loaded = SessionIndex.load(tmp_path / "index.json")
    assert loaded.get("abc-123") is not None
    assert loaded.get("abc-123").bundle == "test-bundle"


def test_atomic_write(tmp_path):
    """Verify tmp+rename pattern — no .tmp file left behind."""
    index = SessionIndex(tmp_path / "index.json")
    index.add(
        SessionIndexEntry(
            session_id="x",
            status="idle",
            bundle="b",
            created_at="2026-03-03T10:00:00Z",
            last_activity="2026-03-03T10:00:00Z",
        )
    )
    index.save()
    assert not (tmp_path / "index.json.tmp").exists()
    assert (tmp_path / "index.json").exists()


def test_rebuild_from_session_dirs(tmp_path):
    """Rebuild index by scanning session directories."""
    sessions_dir = tmp_path / "sessions"
    sid = "abc-123"
    sdir = sessions_dir / sid
    sdir.mkdir(parents=True)
    (sdir / "metadata.json").write_text(
        json.dumps(
            {
                "session_id": sid,
                "bundle": "test",
                "created_at": "2026-03-03T10:00:00Z",
            }
        )
    )
    index = SessionIndex.rebuild(sessions_dir)
    entry = index.get(sid)
    assert entry is not None
    assert entry.bundle == "test"
    assert entry.created_at == "2026-03-03T10:00:00Z"


def test_load_corrupted_falls_back_to_empty(tmp_path):
    (tmp_path / "index.json").write_text("NOT VALID JSON")
    index = SessionIndex.load(tmp_path / "index.json")
    assert index.list_entries() == []


def test_update_entry(tmp_path):
    index = SessionIndex(tmp_path / "index.json")
    index.add(
        SessionIndexEntry(
            session_id="x",
            status="idle",
            bundle="b",
            created_at="2026-03-03T10:00:00Z",
            last_activity="2026-03-03T10:00:00Z",
        )
    )
    result = index.update("x", status="running")
    assert result is True
    assert index.get("x").status == "running"


def test_update_unknown_session_returns_false(tmp_path):
    index = SessionIndex(tmp_path / "index.json")
    result = index.update("nonexistent", status="running")
    assert result is False


def test_update_invalid_field_raises(tmp_path):
    index = SessionIndex(tmp_path / "index.json")
    index.add(
        SessionIndexEntry(
            session_id="x",
            status="idle",
            bundle="b",
            created_at="2026-03-03T10:00:00Z",
            last_activity="2026-03-03T10:00:00Z",
        )
    )
    with pytest.raises(ValueError, match="Unknown"):
        index.update("x", bogus_field="bad")


def test_remove_entry(tmp_path):
    index = SessionIndex(tmp_path / "index.json")
    index.add(
        SessionIndexEntry(
            session_id="x",
            status="idle",
            bundle="b",
            created_at="2026-03-03T10:00:00Z",
            last_activity="2026-03-03T10:00:00Z",
        )
    )
    index.remove("x")
    assert index.get("x") is None


def test_get_missing_returns_none(tmp_path):
    index = SessionIndex(tmp_path / "index.json")
    assert index.get("no-such-id") is None
