import json
from pathlib import Path

import pytest

from notificator.state import load_state, save_state, merge_reminders


# --- load_state ---

def test_load_state_missing_file(tmp_path):
    result = load_state(str(tmp_path / "nonexistent.json"))
    assert result == []


def test_load_state_corrupt_file_returns_empty(tmp_path):
    state_file = tmp_path / "reminders.json"
    state_file.write_text("not valid json{{{")
    result = load_state(str(state_file))
    assert result == []


def test_load_state_returns_list(tmp_path):
    state_file = tmp_path / "reminders.json"
    entries = [
        {
            "id": "tasks/a.md::0",
            "file": "tasks/a.md",
            "title": "A",
            "description": "desc",
            "fire_time": "2026-05-16T09:00:00+00:00",
            "sent_at": None,
        }
    ]
    state_file.write_text(json.dumps(entries))
    result = load_state(str(state_file))
    assert len(result) == 1
    assert result[0]["id"] == "tasks/a.md::0"


# --- save_state ---

def test_save_state_writes_json(tmp_path):
    state_file = tmp_path / "reminders.json"
    entries = [{"id": "tasks/a.md::0", "fire_time": "2026-05-16T09:00:00+00:00", "sent_at": None}]
    save_state(str(state_file), entries)
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert data[0]["id"] == "tasks/a.md::0"


def test_save_state_atomic_no_tmp_left(tmp_path):
    state_file = tmp_path / "reminders.json"
    save_state(str(state_file), [])
    tmp = Path(str(state_file) + ".tmp")
    assert not tmp.exists()


# --- merge_reminders ---

def test_merge_adds_new_entries():
    existing = []
    incoming = [
        {
            "id": "tasks/a.md::0",
            "file": "tasks/a.md",
            "title": "A",
            "description": "d",
            "fire_time": "2026-05-16T09:00:00+00:00",
            "sent_at": None,
        }
    ]
    result = merge_reminders(existing, incoming)
    assert len(result) == 1
    assert result[0]["id"] == "tasks/a.md::0"


def test_merge_preserves_sent_at():
    existing = [
        {
            "id": "tasks/a.md::0",
            "file": "tasks/a.md",
            "title": "A",
            "description": "d",
            "fire_time": "2026-05-16T09:00:00+00:00",
            "sent_at": "2026-05-16T09:00:05+00:00",
        }
    ]
    incoming = [
        {
            "id": "tasks/a.md::0",
            "file": "tasks/a.md",
            "title": "A",
            "description": "d",
            "fire_time": "2026-05-16T09:00:00+00:00",
            "sent_at": None,
        }
    ]
    result = merge_reminders(existing, incoming)
    assert len(result) == 1
    assert result[0]["sent_at"] == "2026-05-16T09:00:05+00:00"


def test_merge_removes_stale_entries():
    existing = [
        {
            "id": "tasks/old.md::0",
            "file": "tasks/old.md",
            "title": "Old",
            "description": "d",
            "fire_time": "2026-05-15T09:00:00+00:00",
            "sent_at": None,
        }
    ]
    incoming = []
    result = merge_reminders(existing, incoming)
    assert result == []


def test_merge_new_and_existing_combined():
    existing = [
        {
            "id": "tasks/a.md::0",
            "file": "tasks/a.md",
            "title": "A",
            "description": "d",
            "fire_time": "2026-05-16T09:00:00+00:00",
            "sent_at": "2026-05-16T09:00:05+00:00",
        }
    ]
    incoming = [
        {
            "id": "tasks/a.md::0",
            "file": "tasks/a.md",
            "title": "A",
            "description": "d",
            "fire_time": "2026-05-16T09:00:00+00:00",
            "sent_at": None,
        },
        {
            "id": "tasks/b.md::0",
            "file": "tasks/b.md",
            "title": "B",
            "description": "d2",
            "fire_time": "2026-05-16T10:00:00+00:00",
            "sent_at": None,
        },
    ]
    result = merge_reminders(existing, incoming)
    assert len(result) == 2
    by_id = {r["id"]: r for r in result}
    assert by_id["tasks/a.md::0"]["sent_at"] == "2026-05-16T09:00:05+00:00"
    assert by_id["tasks/b.md::0"]["sent_at"] is None
