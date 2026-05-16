# Stateful Two-Job Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stateless single-pass loop with two decoupled APScheduler jobs — a scanner that writes pending reminders to a JSON state file, and a sender that reads the file, fires due notifications, and marks them sent.

**Architecture:** One container, one Python process, two APScheduler CronJobs sharing `/data/reminders.json` on a Docker volume. The scanner merges into the state file (preserving `sent_at`); the sender writes `sent_at` only on successful Telegram delivery. State file writes are atomic (tmp → rename).

**Tech Stack:** Python 3.12, APScheduler 3.x (`CronTrigger`), httpx, PyYAML, isodate, pytz, pytest, respx

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `notificator/config.py` | Modify | Add `state_file`, `scanner_cron`, `sender_cron` fields; remove `cron_schedule` |
| `notificator/state.py` | Create | `load_state()`, `save_state()`, `merge_reminders()` |
| `notificator/jobs.py` | Create | `scan_job(config)`, `send_job(config)` |
| `notificator/main.py` | Modify | Register two APScheduler jobs; remove `run_once()` |
| `tests/test_config.py` | Modify | Update tests for new config fields |
| `tests/test_state.py` | Create | Unit tests for state module |
| `tests/test_jobs.py` | Create | Integration tests for scan_job and send_job |
| `docker-compose.yml` | Modify | Add `/data` named volume |
| `.env.example` | Modify | Replace `CRON_SCHEDULE` with `SCANNER_CRON`, `SENDER_CRON`, `STATE_FILE` |

---

## Task 1: Update `config.py` — add stateful fields

**Files:**
- Modify: `notificator/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Replace the content of `tests/test_config.py` with:

```python
import os
import pytest
from notificator.config import Config, ConfigError, load_config


def test_load_config_all_required(monkeypatch):
    monkeypatch.setenv("TASKS_DIR", "/vault/tasks")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.delenv("STATE_FILE", raising=False)
    monkeypatch.delenv("SCANNER_CRON", raising=False)
    monkeypatch.delenv("SENDER_CRON", raising=False)

    config = load_config()

    assert config.tasks_dir == "/vault/tasks"
    assert config.telegram_token == "tok"
    assert config.telegram_chat_id == "123"
    assert config.timezone == "UTC"
    assert config.state_file == "/data/reminders.json"
    assert config.scanner_cron == "0 0 * * *"
    assert config.sender_cron == "* * * * *"


def test_load_config_custom_optional(monkeypatch):
    monkeypatch.setenv("TASKS_DIR", "/vault/tasks")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("STATE_FILE", "/tmp/state.json")
    monkeypatch.setenv("SCANNER_CRON", "0 6 * * *")
    monkeypatch.setenv("SENDER_CRON", "*/5 * * * *")

    config = load_config()

    assert config.state_file == "/tmp/state.json"
    assert config.scanner_cron == "0 6 * * *"
    assert config.sender_cron == "*/5 * * * *"


def test_load_config_missing_required(monkeypatch):
    monkeypatch.delenv("TASKS_DIR", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TIMEZONE", "UTC")

    with pytest.raises(ConfigError, match="TASKS_DIR"):
        load_config()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_config.py -v
```

Expected: FAIL — `Config` has no `state_file` attribute.

- [ ] **Step 3: Update `notificator/config.py`**

```python
import os
from dataclasses import dataclass


class ConfigError(Exception):
    pass


@dataclass
class Config:
    tasks_dir: str
    telegram_token: str
    telegram_chat_id: str
    timezone: str
    state_file: str
    scanner_cron: str
    sender_cron: str


def load_config() -> Config:
    def require(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise ConfigError(f"Required environment variable '{name}' is missing or empty.")
        return value

    return Config(
        tasks_dir=require("TASKS_DIR"),
        telegram_token=require("TELEGRAM_TOKEN"),
        telegram_chat_id=require("TELEGRAM_CHAT_ID"),
        timezone=require("TIMEZONE"),
        state_file=os.environ.get("STATE_FILE", "/data/reminders.json"),
        scanner_cron=os.environ.get("SCANNER_CRON", "0 0 * * *"),
        sender_cron=os.environ.get("SENDER_CRON", "* * * * *"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_config.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add notificator/config.py tests/test_config.py
git commit -m "feat: add state_file, scanner_cron, sender_cron to Config"
```

---

## Task 2: Create `notificator/state.py`

**Files:**
- Create: `notificator/state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_state.py`:

```python
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from notificator.state import load_state, save_state, merge_reminders


# --- load_state ---

def test_load_state_missing_file(tmp_path):
    result = load_state(str(tmp_path / "nonexistent.json"))
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_state.py -v
```

Expected: ERROR — `notificator.state` module not found.

- [ ] **Step 3: Create `notificator/state.py`**

```python
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def load_state(state_file: str) -> list[dict[str, Any]]:
    """Load reminders from the JSON state file. Returns [] if file does not exist."""
    if not os.path.exists(state_file):
        return []
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load state file %s: %s", state_file, e)
        return []


def save_state(state_file: str, entries: list[dict[str, Any]]) -> None:
    """Atomically write entries to the JSON state file via a tmp file rename."""
    tmp_path = state_file + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, default=str)
        os.replace(tmp_path, state_file)
    except Exception as e:
        logger.error("Failed to save state file %s: %s", state_file, e)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def merge_reminders(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge incoming reminders into existing state.
    - Entries in incoming not in existing are added.
    - Entries in existing not in incoming are removed.
    - sent_at from existing is preserved over incoming's null.
    """
    existing_by_id = {e["id"]: e for e in existing}
    result = []
    for entry in incoming:
        eid = entry["id"]
        if eid in existing_by_id and existing_by_id[eid].get("sent_at") is not None:
            merged = dict(entry)
            merged["sent_at"] = existing_by_id[eid]["sent_at"]
            result.append(merged)
        else:
            result.append(dict(entry))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_state.py -v
```

Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add notificator/state.py tests/test_state.py
git commit -m "feat: add state module with load/save/merge"
```

---

## Task 3: Create `notificator/jobs.py`

**Files:**
- Create: `notificator/jobs.py`
- Create: `tests/test_jobs.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_jobs.py`:

```python
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


def test_send_job_retries_on_telegram_error(tmp_path):
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_jobs.py -v
```

Expected: ERROR — `notificator.jobs` module not found.

- [ ] **Step 3: Create `notificator/jobs.py`**

```python
import logging
from datetime import datetime, timezone
from typing import Any

import pytz

from notificator.config import Config
from notificator.reminder import compute_fire_time, ReminderError
from notificator.scanner import scan_tasks
from notificator.state import load_state, merge_reminders, save_state
from notificator.telegram import TelegramError, send_notification

logger = logging.getLogger(__name__)


def scan_job(config: Config) -> None:
    """Scan task files and merge pending reminders into the state file."""
    tz = pytz.timezone(config.timezone)
    today = datetime.now(tz).date()

    tasks = scan_tasks(config.tasks_dir, today)
    logger.info("scan_job: found %d task(s) for today", len(tasks))

    incoming: list[dict[str, Any]] = []
    for task in tasks:
        for idx, reminder in enumerate(task.get("reminders", [])):
            try:
                fire_time = compute_fire_time(reminder, task, tz)
            except ReminderError as e:
                logger.warning("scan_job: skipping reminder %s: %s", idx, e)
                continue

            entry_id = f"{task['file_path']}::{idx}"
            incoming.append({
                "id": entry_id,
                "file": task["file_path"],
                "title": task["title"],
                "description": reminder.get("description", ""),
                "fire_time": fire_time.astimezone(timezone.utc).isoformat(),
                "sent_at": None,
            })

    existing = load_state(config.state_file)
    merged = merge_reminders(existing, incoming)
    save_state(config.state_file, merged)
    logger.info("scan_job: state file updated with %d reminder(s)", len(merged))


def send_job(config: Config) -> None:
    """Send due reminders and mark them sent in the state file."""
    now = datetime.now(timezone.utc)
    entries = load_state(config.state_file)

    updated = False
    for entry in entries:
        if entry.get("sent_at") is not None:
            continue
        fire_time = datetime.fromisoformat(entry["fire_time"])
        if fire_time > now:
            continue

        reminder = {"description": entry.get("description", ""), "id": entry["id"]}
        task = {"title": entry.get("title", ""), "file_path": entry.get("file", "")}

        try:
            send_notification(
                token=config.telegram_token,
                chat_id=config.telegram_chat_id,
                reminder=reminder,
                task=task,
                anchor_value=entry.get("fire_time", ""),
            )
            entry["sent_at"] = now.isoformat()
            updated = True
            logger.info("send_job: sent reminder '%s'", entry["id"])
        except TelegramError as e:
            logger.error("send_job: failed to send reminder '%s': %s", entry["id"], e)

    if updated:
        save_state(config.state_file, entries)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_jobs.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add notificator/jobs.py tests/test_jobs.py
git commit -m "feat: add jobs module with scan_job and send_job"
```

---

## Task 4: Update `notificator/main.py`

**Files:**
- Modify: `notificator/main.py`

- [ ] **Step 1: Replace `main.py` content**

```python
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from notificator.config import ConfigError, load_config
from notificator.jobs import scan_job, send_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        config = load_config()
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        raise SystemExit(1)

    logger.info("Starting notificator")
    logger.info("  scanner_cron : %s", config.scanner_cron)
    logger.info("  sender_cron  : %s", config.sender_cron)
    logger.info("  state_file   : %s", config.state_file)

    scheduler = BlockingScheduler(timezone=config.timezone)

    scheduler.add_job(
        scan_job,
        CronTrigger.from_crontab(config.scanner_cron, timezone=config.timezone),
        args=[config],
        id="scan_job",
        name="Scanner",
    )
    scheduler.add_job(
        send_job,
        CronTrigger.from_crontab(config.sender_cron, timezone=config.timezone),
        args=[config],
        id="send_job",
        name="Sender",
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Notificator stopped.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run full test suite to confirm no regressions**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests PASSED (existing 16 + new state + jobs tests).

- [ ] **Step 3: Commit**

```bash
git add notificator/main.py
git commit -m "feat: replace run_once with two APScheduler jobs in main"
```

---

## Task 5: Update infra files (docker-compose, .env.example)

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Update `docker-compose.yml`** to add the `/data` named volume:

```yaml
services:
  notificator:
    image: ghcr.io/${GITHUB_REPOSITORY_OWNER:-local}/obsidian-tasks-notificator:latest
    build:
      context: .
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ${TASKS_DIR_HOST}:/vault/tasks:ro
      - notificator_data:/data

volumes:
  notificator_data:
```

- [ ] **Step 2: Update `.env.example`** — replace `CRON_SCHEDULE` with the three new vars:

```
TASKS_DIR=/vault/tasks
TASKS_DIR_HOST=/path/to/obsidian/vault/tasks
TELEGRAM_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
TIMEZONE=Europe/Warsaw
STATE_FILE=/data/reminders.json
SCANNER_CRON=0 0 * * *
SENDER_CRON=* * * * *
```

- [ ] **Step 3: Run full test suite to confirm nothing broken**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests PASSED.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "chore: add /data volume and update env vars for stateful design"
```

---

## Task 6: Full verification

- [ ] **Step 1: Run complete test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests PASSED with no warnings about unknown marks or missing modules.

- [ ] **Step 2: Verify the old `CRON_SCHEDULE` env var is fully removed**

```bash
grep -r "CRON_SCHEDULE\|cron_schedule\b\|run_once" notificator/ tests/
```

Expected: No matches (old stateless code fully gone).

- [ ] **Step 3: Commit final cleanup if any**

```bash
git add -A
git commit -m "chore: verify stateful redesign complete"
```
