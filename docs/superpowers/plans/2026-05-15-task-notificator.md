# Obsidian Tasks Notificator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a containerized Python service that scans an Obsidian vault task directory every minute, computes reminder fire times, and sends Telegram notifications when a reminder is due.

**Architecture:** A cron-driven Python package (`notificator/`) runs inside Docker; each tick it globs `*.md` files, reads only frontmatter, filters by today's date and non-done status, computes fire times for each reminder, and POSTs to the Telegram Bot API if the fire time falls within the current minute window. CI/CD via GitHub Actions: test → build → push to ghcr.io → SSH deploy to VPS.

**Tech Stack:** Python 3.12, PyYAML, isodate, python-dateutil, pytz, httpx, APScheduler, Docker, GitHub Actions

---

## File Map

```
obsidian-tasks-notificator/
├── notificator/
│   ├── __init__.py
│   ├── config.py        # Loads + validates env vars
│   ├── scanner.py       # Globs files, reads frontmatter, filters today/non-done
│   ├── reminder.py      # Computes fire datetime from reminder spec
│   ├── telegram.py      # Sends Telegram message via Bot API
│   └── main.py          # Entry point: orchestrate scan → filter → notify
├── tests/
│   ├── __init__.py
│   ├── test_scanner.py
│   ├── test_reminder.py
│   └── test_telegram.py
├── tasks/               # Sample task files (already exists)
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── pyproject.toml
└── .github/
    └── workflows/
        └── ci-cd.yml
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `notificator/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "obsidian-tasks-notificator"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "PyYAML>=6.0",
    "isodate>=0.6.1",
    "python-dateutil>=2.9",
    "pytz>=2024.1",
    "httpx>=0.27",
    "APScheduler>=3.10",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.14",
]

[tool.hatch.build.targets.wheel]
packages = ["notificator"]
```

- [ ] **Step 2: Create empty package init files**

`notificator/__init__.py` — empty file.

`tests/__init__.py` — empty file.

- [ ] **Step 3: Install dependencies**

```bash
pip install -e ".[dev]"
```

Expected: installs all dependencies without errors.

- [ ] **Step 4: Verify pytest can discover tests**

```bash
pytest tests/ -v
```

Expected: `no tests ran` (0 errors).

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml notificator/__init__.py tests/__init__.py
git commit -m "chore: scaffold project structure"
```

---

## Task 2: Configuration loader

**Files:**
- Create: `notificator/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config.py`:

```python
import pytest
import os
from notificator.config import load_config, ConfigError


def test_load_config_success(monkeypatch):
    monkeypatch.setenv("TASKS_DIR", "/vault/tasks")
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setenv("TIMEZONE", "Europe/Warsaw")

    cfg = load_config()

    assert cfg.tasks_dir == "/vault/tasks"
    assert cfg.telegram_token == "123:ABC"
    assert cfg.telegram_chat_id == "999"
    assert cfg.timezone == "Europe/Warsaw"
    assert cfg.cron_schedule == "* * * * *"  # default


def test_load_config_custom_cron(monkeypatch):
    monkeypatch.setenv("TASKS_DIR", "/vault/tasks")
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("CRON_SCHEDULE", "*/5 * * * *")

    cfg = load_config()

    assert cfg.cron_schedule == "*/5 * * * *"


def test_load_config_missing_required(monkeypatch):
    for key in ("TASKS_DIR", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "TIMEZONE"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigError, match="TASKS_DIR"):
        load_config()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `config` not yet implemented.

- [ ] **Step 3: Implement `notificator/config.py`**

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
    cron_schedule: str


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
        cron_schedule=os.environ.get("CRON_SCHEDULE", "* * * * *"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add notificator/config.py tests/test_config.py
git commit -m "feat: add configuration loader with env var validation"
```

---

## Task 3: Task file scanner

**Files:**
- Create: `notificator/scanner.py`
- Create: `tests/test_scanner.py`
- Create: `tests/fixtures/task_today.md`
- Create: `tests/fixtures/task_done.md`
- Create: `tests/fixtures/task_other_day.md`
- Create: `tests/fixtures/task_no_frontmatter.md`

- [ ] **Step 1: Create fixture files**

`tests/fixtures/task_today.md` — use today's date (the tests will inject the date dynamically, so use a placeholder value here that tests will override):

```markdown
---
title: Today Task
status: todo
scheduled: 2026-05-15
due: 2026-05-15
reminders:
  - id: rem_001
    type: relative
    description: 0 minute before
    relatedTo: scheduled
    offset: "-PT0M"
---
```

`tests/fixtures/task_done.md`:

```markdown
---
title: Done Task
status: done
scheduled: 2026-05-15
due: 2026-05-15
reminders:
  - id: rem_002
    type: relative
    description: 30 minutes before
    relatedTo: scheduled
    offset: "-PT30M"
---
```

`tests/fixtures/task_other_day.md`:

```markdown
---
title: Other Day Task
status: todo
scheduled: 2020-01-01
due: 2020-01-01
reminders:
  - id: rem_003
    type: relative
    description: 1 hour before
    relatedTo: due
    offset: "-PT1H"
---
```

`tests/fixtures/task_no_frontmatter.md`:

```markdown
Just some notes without frontmatter.
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_scanner.py`:

```python
import pytest
from pathlib import Path
from datetime import date
from notificator.scanner import scan_tasks

FIXTURES = Path(__file__).parent / "fixtures"


def test_returns_today_non_done_tasks(monkeypatch):
    today = date(2026, 5, 15)
    tasks = scan_tasks(str(FIXTURES), today)
    titles = [t["title"] for t in tasks]
    assert "Today Task" in titles


def test_skips_done_tasks(monkeypatch):
    today = date(2026, 5, 15)
    tasks = scan_tasks(str(FIXTURES), today)
    titles = [t["title"] for t in tasks]
    assert "Done Task" not in titles


def test_skips_other_day_tasks():
    today = date(2026, 5, 15)
    tasks = scan_tasks(str(FIXTURES), today)
    titles = [t["title"] for t in tasks]
    assert "Other Day Task" not in titles


def test_skips_files_without_frontmatter():
    today = date(2026, 5, 15)
    # should not raise, just skip
    tasks = scan_tasks(str(FIXTURES), today)
    titles = [t["title"] for t in tasks]
    assert all(t is not None for t in tasks)


def test_task_has_required_fields():
    today = date(2026, 5, 15)
    tasks = scan_tasks(str(FIXTURES), today)
    task = next(t for t in tasks if t["title"] == "Today Task")
    assert "title" in task
    assert "status" in task
    assert "reminders" in task
    assert "file_path" in task
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_scanner.py -v
```

Expected: `ImportError` — `scanner` not yet implemented.

- [ ] **Step 4: Implement `notificator/scanner.py`**

```python
import glob
import logging
from datetime import date
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _read_frontmatter(path: str) -> dict[str, Any] | None:
    """Read only the YAML frontmatter from a .md file (stops at closing ---)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline()
            if first_line.strip() != "---":
                return None
            lines = []
            for line in f:
                if line.strip() == "---":
                    break
                lines.append(line)
        return yaml.safe_load("".join(lines)) or {}
    except Exception as e:
        logger.warning("Failed to read frontmatter from %s: %s", path, e)
        return None


def scan_tasks(tasks_dir: str, today: date) -> list[dict[str, Any]]:
    """Return task dicts for non-done tasks scheduled or due today."""
    results = []
    pattern = str(Path(tasks_dir) / "*.md")
    for path in glob.glob(pattern):
        fm = _read_frontmatter(path)
        if fm is None:
            continue
        if fm.get("status") == "done":
            continue
        scheduled = fm.get("scheduled")
        due = fm.get("due")
        # yaml may parse date fields as date objects already
        def to_date(val):
            if isinstance(val, date):
                return val
            if isinstance(val, str):
                try:
                    from datetime import datetime
                    return datetime.strptime(val, "%Y-%m-%d").date()
                except ValueError:
                    return None
            return None

        scheduled_date = to_date(scheduled)
        due_date = to_date(due)

        if scheduled_date != today and due_date != today:
            continue

        results.append({
            "title": fm.get("title", Path(path).stem),
            "status": fm.get("status"),
            "scheduled": scheduled_date,
            "due": due_date,
            "reminders": fm.get("reminders") or [],
            "file_path": path,
        })
    return results
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_scanner.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add notificator/scanner.py tests/test_scanner.py tests/fixtures/
git commit -m "feat: add task file scanner with frontmatter-only parsing"
```

---

## Task 4: Reminder fire time calculator

**Files:**
- Create: `notificator/reminder.py`
- Create: `tests/test_reminder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_reminder.py`:

```python
import pytest
from datetime import datetime, date
import pytz
from notificator.reminder import compute_fire_time, ReminderError

TZ = pytz.timezone("Europe/Warsaw")


def _task(scheduled=None, due=None):
    return {
        "title": "Test Task",
        "scheduled": scheduled,
        "due": due,
        "file_path": "/vault/tasks/test.md",
    }


def test_relative_zero_offset_scheduled():
    task = _task(scheduled=date(2026, 5, 15))
    reminder = {
        "id": "rem_1",
        "type": "relative",
        "description": "0 minute before",
        "relatedTo": "scheduled",
        "offset": "-PT0M",
    }
    fire = compute_fire_time(reminder, task, TZ)
    expected = TZ.localize(datetime(2026, 5, 15, 0, 0, 0))
    assert fire == expected


def test_relative_30min_before_scheduled():
    task = _task(scheduled=date(2026, 5, 15))
    reminder = {
        "id": "rem_2",
        "type": "relative",
        "description": "30 minutes before",
        "relatedTo": "scheduled",
        "offset": "-PT30M",
    }
    fire = compute_fire_time(reminder, task, TZ)
    expected = TZ.localize(datetime(2026, 5, 14, 23, 30, 0))
    assert fire == expected


def test_relative_1h_after_due():
    task = _task(due=date(2026, 5, 15))
    reminder = {
        "id": "rem_3",
        "type": "relative",
        "description": "1 hour after due",
        "relatedTo": "due",
        "offset": "PT1H",
    }
    fire = compute_fire_time(reminder, task, TZ)
    expected = TZ.localize(datetime(2026, 5, 15, 1, 0, 0))
    assert fire == expected


def test_absolute_reminder():
    task = _task()
    reminder = {
        "id": "rem_4",
        "type": "absolute",
        "description": "fixed time",
        "datetime": "2026-05-15T10:30:00+02:00",
    }
    fire = compute_fire_time(reminder, task, TZ)
    assert fire.hour == 10
    assert fire.minute == 30


def test_unknown_type_raises():
    task = _task(scheduled=date(2026, 5, 15))
    reminder = {"id": "rem_5", "type": "unknown", "description": "x"}
    with pytest.raises(ReminderError, match="Unknown reminder type"):
        compute_fire_time(reminder, task, TZ)


def test_missing_anchor_field_raises():
    task = _task()  # no scheduled, no due
    reminder = {
        "id": "rem_6",
        "type": "relative",
        "description": "x",
        "relatedTo": "scheduled",
        "offset": "-PT0M",
    }
    with pytest.raises(ReminderError, match="Anchor field 'scheduled' not found"):
        compute_fire_time(reminder, task, TZ)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_reminder.py -v
```

Expected: `ImportError` — `reminder` not yet implemented.

- [ ] **Step 3: Implement `notificator/reminder.py`**

```python
import logging
from datetime import date, datetime, timezone
from typing import Any

import isodate
import pytz

logger = logging.getLogger(__name__)


class ReminderError(Exception):
    pass


def compute_fire_time(
    reminder: dict[str, Any],
    task: dict[str, Any],
    tz: pytz.BaseTzInfo,
) -> datetime:
    """
    Compute the timezone-aware datetime at which a reminder should fire.

    Raises ReminderError for unknown types or missing anchor fields.
    """
    rtype = reminder.get("type")

    if rtype == "relative":
        anchor_field = reminder.get("relatedTo")
        anchor_value = task.get(anchor_field)
        if anchor_value is None:
            raise ReminderError(
                f"Anchor field '{anchor_field}' not found in task '{task.get('title')}'"
            )

        # Normalize anchor to a timezone-aware datetime
        if isinstance(anchor_value, date) and not isinstance(anchor_value, datetime):
            anchor_dt = tz.localize(datetime(anchor_value.year, anchor_value.month, anchor_value.day))
        elif isinstance(anchor_value, datetime):
            if anchor_value.tzinfo is None:
                anchor_dt = tz.localize(anchor_value)
            else:
                anchor_dt = anchor_value.astimezone(tz)
        else:
            raise ReminderError(
                f"Cannot convert anchor field '{anchor_field}' value '{anchor_value}' to datetime"
            )

        offset_str = reminder.get("offset", "PT0S")
        try:
            duration = isodate.parse_duration(offset_str)
        except Exception as e:
            raise ReminderError(f"Invalid ISO 8601 duration '{offset_str}': {e}") from e

        return anchor_dt + duration

    elif rtype == "absolute":
        dt_str = reminder.get("datetime")
        if not dt_str:
            raise ReminderError("Absolute reminder missing 'datetime' field")
        try:
            dt = isodate.parse_datetime(dt_str)
        except Exception as e:
            raise ReminderError(f"Invalid datetime '{dt_str}': {e}") from e
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        return dt.astimezone(tz)

    else:
        raise ReminderError(f"Unknown reminder type '{rtype}'")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_reminder.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add notificator/reminder.py tests/test_reminder.py
git commit -m "feat: add reminder fire time calculator (relative + absolute)"
```

---

## Task 5: Telegram notifier

**Files:**
- Create: `notificator/telegram.py`
- Create: `tests/test_telegram.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_telegram.py`:

```python
import pytest
import httpx
from unittest.mock import patch, MagicMock
from notificator.telegram import send_notification, TelegramError


def _reminder():
    return {"description": "0 minute before", "relatedTo": "scheduled"}


def _task():
    return {
        "title": "My Task",
        "scheduled": None,
        "due": None,
        "file_path": "/vault/tasks/my-task.md",
    }


def test_send_notification_calls_api(respx_mock):
    import respx
    route = respx_mock.post("https://api.telegram.org/bot123:ABC/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    send_notification(
        token="123:ABC",
        chat_id="999",
        reminder=_reminder(),
        task=_task(),
        anchor_value="2026-05-15",
    )
    assert route.called


def test_send_notification_raises_on_api_error(respx_mock):
    respx_mock.post("https://api.telegram.org/bot123:ABC/sendMessage").mock(
        return_value=httpx.Response(400, json={"ok": False, "description": "Bad Request"})
    )
    with pytest.raises(TelegramError, match="400"):
        send_notification(
            token="123:ABC",
            chat_id="999",
            reminder=_reminder(),
            task=_task(),
            anchor_value="2026-05-15",
        )
```

- [ ] **Step 2: Install respx for httpx mocking**

Add `respx>=0.20` to dev dependencies in `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.14",
    "respx>=0.20",
]
```

Then:

```bash
pip install -e ".[dev]"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_telegram.py -v
```

Expected: `ImportError` — `telegram` not yet implemented.

- [ ] **Step 4: Implement `notificator/telegram.py`**

```python
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramError(Exception):
    pass


def _format_message(
    reminder: dict[str, Any],
    task: dict[str, Any],
    anchor_value: Any,
) -> str:
    anchor_field = reminder.get("relatedTo", "")
    file_path = task.get("file_path", "")
    return (
        f"Reminder: {reminder.get('description', '')}\n"
        f"Task: {task.get('title', '')}\n"
        f"Anchor: {anchor_field}: {anchor_value}\n"
        f"File: {file_path}"
    )


def send_notification(
    token: str,
    chat_id: str,
    reminder: dict[str, Any],
    task: dict[str, Any],
    anchor_value: Any,
) -> None:
    """Send a Telegram message for a fired reminder. Raises TelegramError on failure."""
    text = _format_message(reminder, task, anchor_value)
    url = TELEGRAM_API.format(token=token)
    response = httpx.post(url, json={"chat_id": chat_id, "text": text})
    if not response.is_success:
        raise TelegramError(
            f"Telegram API returned {response.status_code}: {response.text}"
        )
    logger.info("Notification sent for task '%s', reminder '%s'", task.get("title"), reminder.get("id"))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_telegram.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add notificator/telegram.py tests/test_telegram.py pyproject.toml
git commit -m "feat: add Telegram notifier"
```

---

## Task 6: Main orchestrator

**Files:**
- Create: `notificator/main.py`

- [ ] **Step 1: Implement `notificator/main.py`**

```python
import logging
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

from notificator.config import load_config, ConfigError
from notificator.reminder import compute_fire_time, ReminderError
from notificator.scanner import scan_tasks
from notificator.telegram import send_notification, TelegramError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WINDOW_SECONDS = 30


def run_once(config) -> None:
    tz = pytz.timezone(config.timezone)
    now = datetime.now(tz)
    today = now.date()

    tasks = scan_tasks(config.tasks_dir, today)
    logger.info("Found %d task(s) for today", len(tasks))

    for task in tasks:
        for reminder in task["reminders"]:
            try:
                fire_time = compute_fire_time(reminder, task, tz)
            except ReminderError as e:
                logger.warning("Skipping reminder %s: %s", reminder.get("id"), e)
                continue

            delta = abs((fire_time - now).total_seconds())
            if delta > WINDOW_SECONDS:
                continue

            anchor_field = reminder.get("relatedTo", "")
            anchor_value = task.get(anchor_field) or reminder.get("datetime", "")

            try:
                send_notification(
                    token=config.telegram_token,
                    chat_id=config.telegram_chat_id,
                    reminder=reminder,
                    task=task,
                    anchor_value=anchor_value,
                )
            except TelegramError as e:
                logger.error("Failed to send notification for reminder %s: %s", reminder.get("id"), e)


def main() -> None:
    try:
        config = load_config()
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        raise SystemExit(1)

    logger.info("Starting notificator with schedule: %s", config.cron_schedule)

    # Parse cron expression fields: minute, hour, day, month, day_of_week
    parts = config.cron_schedule.split()
    if len(parts) != 5:
        logger.error("Invalid CRON_SCHEDULE '%s': must have 5 fields", config.cron_schedule)
        raise SystemExit(1)
    minute, hour, day, month, day_of_week = parts

    scheduler = BlockingScheduler(timezone=config.timezone)
    scheduler.add_job(
        run_once,
        "cron",
        args=[config],
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Notificator stopped.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test the entry point (no network)**

Set dummy env vars and confirm it starts without crashing:

```bash
TASKS_DIR=./tasks TELEGRAM_TOKEN=fake TELEGRAM_CHAT_ID=0 TIMEZONE=UTC python -c "
from notificator.config import load_config
from notificator.main import run_once
import os
os.environ['TASKS_DIR'] = './tasks'
os.environ['TELEGRAM_TOKEN'] = 'fake'
os.environ['TELEGRAM_CHAT_ID'] = '0'
os.environ['TIMEZONE'] = 'UTC'
cfg = load_config()
run_once(cfg)
print('OK')
"
```

Expected: prints `OK` (no Telegram calls because no reminders fire now).

- [ ] **Step 3: Commit**

```bash
git add notificator/main.py
git commit -m "feat: add main orchestrator with APScheduler cron loop"
```

---

## Task 7: Dockerfile and docker-compose

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY notificator/ notificator/

RUN pip install --no-cache-dir .

CMD ["python", "-m", "notificator.main"]
```

- [ ] **Step 2: Create `docker-compose.yml`**

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
```

Note: `TASKS_DIR_HOST` is the host path to the Obsidian tasks folder (set in `.env`). `TASKS_DIR` inside the container must be set to `/vault/tasks`.

- [ ] **Step 3: Create `.env.example`**

```dotenv
TASKS_DIR=/vault/tasks
TASKS_DIR_HOST=/path/to/obsidian/vault/tasks
TELEGRAM_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
TIMEZONE=Europe/Warsaw
CRON_SCHEDULE=* * * * *
```

- [ ] **Step 4: Build and run locally**

```bash
cp .env.example .env
# Edit .env with real values, then:
docker compose build
docker compose up
```

Expected: container starts, logs show `Starting notificator with schedule: * * * * *`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .env.example
git commit -m "chore: add Dockerfile and docker-compose for containerized deployment"
```

---

## Task 8: GitHub Actions CI/CD pipeline

**Files:**
- Create: `.github/workflows/ci-cd.yml`

- [ ] **Step 1: Create `.github/workflows/ci-cd.yml`**

```yaml
name: CI/CD

on:
  push:
    branches: [main]

jobs:
  test:
    name: Test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run tests
        run: pytest tests/ -v

  build-push:
    name: Build & Push
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ github.sha }}

  deploy:
    name: Deploy to VPS
    needs: build-push
    runs-on: ubuntu-latest
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd ${{ secrets.VPS_DEPLOY_PATH }}
            docker compose pull
            docker compose up -d
```

- [ ] **Step 2: Add required GitHub secrets**

In the GitHub repository go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `VPS_HOST` | IP or hostname of your VPS |
| `VPS_USER` | SSH username (e.g. `ubuntu`) |
| `VPS_SSH_KEY` | Contents of the private SSH key |
| `VPS_DEPLOY_PATH` | Absolute path on VPS where `docker-compose.yml` lives |

- [ ] **Step 3: Ensure VPS is ready**

On the VPS, verify:

```bash
# Docker and docker compose available
docker --version && docker compose version

# Deploy directory exists with docker-compose.yml and .env
ls $VPS_DEPLOY_PATH

# SSH public key in authorized_keys for VPS_USER
cat ~/.ssh/authorized_keys
```

- [ ] **Step 4: Push to main and verify pipeline**

```bash
git add .github/
git commit -m "ci: add GitHub Actions CI/CD pipeline"
git push origin main
```

Expected: GitHub Actions runs `test → build-push → deploy` all green.

---

## Task 9: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests pass (test_config, test_scanner, test_reminder, test_telegram).

- [ ] **Step 2: Verify Docker build locally**

```bash
docker compose build
```

Expected: image builds without errors.

- [ ] **Step 3: Final commit if any loose files**

```bash
git status
# Add and commit anything uncommitted
```
