import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from notificator.config import Config
from notificator.jobs import scan_job, send_job


def make_config(tmp_path, tasks_dir=None):
    return Config(
        tasks_dir=str(tasks_dir or tmp_path / "tasks"),
        telegram_token="tok",
        telegram_chat_id="123",
        telegram_topic_id=None,
        timezone="UTC",
        state_file=str(tmp_path / "reminders.json"),
        scanner_cron="0 0 * * *",
        sender_cron="* * * * *",
    )


def write_task(tasks_dir: Path, name: str, content: str):
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / name).write_text(content)


# --- scan_job ---

def test_scan_job_writes_state_file(tmp_path):
    tasks_dir = tmp_path / "tasks"
    today = datetime.now(timezone.utc).date().isoformat()
    write_task(tasks_dir, "a.md", f"""---
title: Task A
scheduled: {today}
reminders:
  - type: absolute
    description: test reminder
    datetime: "{today}T09:00:00+00:00"
---
""")
    config = make_config(tmp_path, tasks_dir)
    scan_job(config)
    assert Path(config.state_file).exists()
    state = json.loads(Path(config.state_file).read_text())
    assert len(state) == 1
    assert state[0]["title"] == "Task A"
    assert state[0]["sent_at"] is None


def test_scan_job_preserves_sent_at(tmp_path):
    tasks_dir = tmp_path / "tasks"
    today = datetime.now(timezone.utc).date().isoformat()
    write_task(tasks_dir, "a.md", f"""---
title: Task A
scheduled: {today}
reminders:
  - type: absolute
    description: test reminder
    datetime: "{today}T09:00:00+00:00"
---
""")
    config = make_config(tmp_path, tasks_dir)
    # Pre-populate state with sent_at
    existing = [{
        "id": f"{config.tasks_dir}/a.md::0",
        "file": f"{config.tasks_dir}/a.md",
        "title": "Task A",
        "description": "test reminder",
        "fire_time": f"{today}T09:00:00+00:00",
        "sent_at": "2026-05-16T09:00:05+00:00",
    }]
    Path(config.state_file).write_text(json.dumps(existing))
    scan_job(config)
    state = json.loads(Path(config.state_file).read_text())
    assert state[0]["sent_at"] == "2026-05-16T09:00:05+00:00"


def test_scan_job_empty_tasks_dir(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    config = make_config(tmp_path, tasks_dir)
    scan_job(config)
    state = json.loads(Path(config.state_file).read_text())
    assert state == []


# --- send_job ---

def test_send_job_sends_due_reminders(tmp_path):
    config = make_config(tmp_path)
    now = datetime.now(timezone.utc)
    past = (now - timedelta(minutes=1)).isoformat()
    state = [{
        "id": "tasks/a.md::0",
        "file": "tasks/a.md",
        "title": "Task A",
        "description": "reminder desc",
        "fire_time": past,
        "sent_at": None,
    }]
    Path(config.state_file).write_text(json.dumps(state))

    with patch("notificator.jobs.send_notification") as mock_send:
        send_job(config)
        assert mock_send.call_count == 1

    updated = json.loads(Path(config.state_file).read_text())
    assert updated[0]["sent_at"] is not None


def test_send_job_passes_topic_id_to_send_notification(tmp_path, monkeypatch):
    """send_job passes config.telegram_topic_id to send_notification."""
    import json
    from datetime import datetime, timezone, timedelta
    from notificator.jobs import send_job
    from notificator.config import Config

    state = [{
        "id": "f::0",
        "file": str(tmp_path / "t.md"),
        "title": "T",
        "status": "open",
        "priority": None,
        "scheduled": None,
        "due": None,
        "projects": [],
        "contexts": [],
        "time_estimate": None,
        "recurrence": None,
        "description": "",
        "reminder_type": "relative",
        "offset": "-PT0M",
        "fire_time": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        "sent_at": None,
    }]
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state))

    config = Config(
        tasks_dir=str(tmp_path),
        telegram_token="tok",
        telegram_chat_id="chat",
        telegram_topic_id="99",
        timezone="UTC",
        state_file=str(state_file),
        scanner_cron="*/10 * * * *",
        sender_cron="* * * * *",
    )

    calls = []
    monkeypatch.setattr(
        "notificator.jobs.send_notification",
        lambda **kwargs: calls.append(kwargs),
    )
    send_job(config)
    assert calls[0]["topic_id"] == "99"


def test_send_job_skips_already_sent(tmp_path):
    config = make_config(tmp_path)
    now = datetime.now(timezone.utc)
    past = (now - timedelta(minutes=1)).isoformat()
    state = [{
        "id": "tasks/a.md::0",
        "file": "tasks/a.md",
        "title": "Task A",
        "description": "reminder desc",
        "fire_time": past,
        "sent_at": "2026-05-16T09:00:05+00:00",
    }]
    Path(config.state_file).write_text(json.dumps(state))

    with patch("notificator.jobs.send_notification") as mock_send:
        send_job(config)
        assert mock_send.call_count == 0


def test_send_job_skips_future_reminders(tmp_path):
    config = make_config(tmp_path)
    now = datetime.now(timezone.utc)
    future = (now + timedelta(hours=1)).isoformat()
    state = [{
        "id": "tasks/a.md::0",
        "file": "tasks/a.md",
        "title": "Task A",
        "description": "reminder desc",
        "fire_time": future,
        "sent_at": None,
    }]
    Path(config.state_file).write_text(json.dumps(state))

    with patch("notificator.jobs.send_notification") as mock_send:
        send_job(config)
        assert mock_send.call_count == 0


def test_send_job_does_not_mark_sent_on_telegram_error(tmp_path):
    from notificator.telegram import TelegramError
    config = make_config(tmp_path)
    now = datetime.now(timezone.utc)
    past = (now - timedelta(minutes=1)).isoformat()
    state = [{
        "id": "tasks/a.md::0",
        "file": "tasks/a.md",
        "title": "Task A",
        "description": "reminder desc",
        "fire_time": past,
        "sent_at": None,
    }]
    Path(config.state_file).write_text(json.dumps(state))

    with patch("notificator.jobs.send_notification", side_effect=TelegramError("fail")):
        send_job(config)

    updated = json.loads(Path(config.state_file).read_text())
    assert updated[0]["sent_at"] is None  # not marked sent on failure


def test_send_job_handles_naive_fire_time(tmp_path):
    config = make_config(tmp_path)
    now = datetime.now(timezone.utc)
    # naive datetime string (no UTC offset) — 1 minute in the past
    past_naive = (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")
    state = [{
        "id": "tasks/a.md::0",
        "file": "tasks/a.md",
        "title": "Task A",
        "description": "reminder desc",
        "fire_time": past_naive,
        "sent_at": None,
    }]
    Path(config.state_file).write_text(json.dumps(state))

    with patch("notificator.jobs.send_notification") as mock_send:
        send_job(config)
        assert mock_send.call_count == 1
