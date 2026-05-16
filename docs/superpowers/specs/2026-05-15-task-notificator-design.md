# Design: Obsidian Tasks Notificator

**Date:** 2026-05-15

## Overview

A containerized Python service that runs every minute via cron, scans an Obsidian vault task directory for today's tasks, evaluates their reminders, and sends Telegram notifications when a reminder fires.

---

## Architecture

```
obsidian-tasks-notificator/
├── notificator/
│   ├── __init__.py
│   ├── config.py        # Loads and validates env vars at startup
│   ├── scanner.py       # Globs task files; reads only frontmatter; filters by today's date
│   ├── reminder.py      # Computes fire datetime from reminder spec (relative + absolute)
│   ├── telegram.py      # Sends Telegram message via Bot API
│   └── main.py          # Entry point: orchestrates scan → filter → notify
├── tasks/               # Obsidian vault tasks directory (mounted as Docker volume)
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── pyproject.toml
```

---

## Components

### `config.py`
Loads all configuration from environment variables. Fails fast with a clear error message if any required variable is missing.

### `scanner.py`
1. Globs all `*.md` files in `TASKS_DIR`.
2. For each file, reads bytes only up to the closing `---` of the frontmatter (stops early — does not read the full file).
3. Parses frontmatter via `python-frontmatter` or `PyYAML`.
4. Filters files where:
   - `scheduled` OR `due` date == today (local date per `TIMEZONE`)
   - `status != done`
5. Returns a list of task dicts with: `title`, `status`, `scheduled`, `due`, `reminders`, `file_path`.

### `reminder.py`
Computes the fire datetime for a single reminder entry.

- **Relative** (`type: relative`):
  - `relatedTo` names the anchor field (`scheduled`, `due`, `dateCreated`, etc.)
  - `offset` is an ISO 8601 duration string (e.g. `-PT30M`, `PT1H`)
  - Fire time = anchor datetime + offset
  - Date-only anchor values (e.g. `2026-05-04`) are interpreted as midnight in `TIMEZONE`
- **Absolute** (`type: absolute`):
  - Has a `datetime` field (ISO 8601 datetime string)
  - Fire time = that datetime directly
- Unknown types are logged as a warning and skipped.

### `telegram.py`
Sends a message to the configured chat using the Telegram Bot API (`sendMessage`). Message format:

```
Reminder: <reminder.description>
Task: <task.title>
Anchor: <relatedTo field name>: <anchor value>
File: <relative file path>
```

### `main.py`
Orchestrates the full flow:
1. Load config
2. Scan tasks for today
3. For each task, for each reminder:
   a. Compute fire time
   b. Check if fire time falls within `[now - 30s, now + 30s]`
   c. If yes, send Telegram notification
4. Log each sent notification and any errors

---

## Data Flow

```
cron (every minute)
  └─> main.py
        ├─> scanner.py  →  list of today's non-done task dicts
        ├─> reminder.py →  fire datetime per reminder
        └─> telegram.py →  HTTP POST to Telegram Bot API
```

---

## Configuration (Environment Variables)

| Variable | Required | Description | Example |
|---|---|---|---|
| `TASKS_DIR` | yes | Absolute path to the vault tasks directory | `/vault/tasks` |
| `TELEGRAM_TOKEN` | yes | Telegram Bot API token | `123456:ABC-...` |
| `TELEGRAM_CHAT_ID` | yes | Chat or user ID to send notifications to | `987654321` |
| `TIMEZONE` | yes | Local timezone for date comparisons | `Europe/Warsaw` |
| `CRON_SCHEDULE` | no | Cron expression (default: every minute) | `* * * * *` |

---

## Deduplication Strategy

Stateless, time-window based. A reminder fires if its computed fire time falls within a 60-second window centered on the current minute (`[now - 30s, now + 30s]`). No database or state file is required. If the container restarts mid-minute a notification may be sent twice, which is acceptable.

---

## Error Handling

- Missing required env vars → log error, exit with non-zero code at startup
- File read/parse error for a specific task file → log warning, skip file, continue
- Unknown reminder type → log warning, skip reminder, continue
- Telegram API error → log error with HTTP status, continue (do not crash the run)

---

## Container Setup

- **Dockerfile**: Python 3.12 slim image; installs dependencies via `pyproject.toml`; copies `notificator/` package
- **docker-compose.yml**: Mounts the vault tasks directory as a read-only volume at `/vault/tasks`; loads `.env` for secrets; runs the cron scheduler
- Cron is managed inside the container (via `crond` or a Python scheduler like `APScheduler`) — no host cron dependency

---

## CI/CD (GitHub Actions)

### Pipeline: `.github/workflows/ci-cd.yml`

Triggered on every push to `main`.

**Stages:**

1. **Test** — runs `pytest` against the `notificator/` package inside a Python 3.12 environment
2. **Build & Push** — builds the Docker image and pushes to `ghcr.io/<owner>/obsidian-tasks-notificator:latest` (and a SHA tag for traceability)
3. **Deploy** — SSHes into the VPS and runs:
   ```bash
   docker compose pull && docker compose up -d
   ```

Stages run sequentially; deploy only runs if test and build pass.

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `VPS_HOST` | VPS IP or hostname |
| `VPS_USER` | SSH username |
| `VPS_SSH_KEY` | Private SSH key for VPS access |
| `VPS_DEPLOY_PATH` | Absolute path to `docker-compose.yml` on VPS |

Image credentials for `ghcr.io` use `GITHUB_TOKEN` (automatically available in Actions — no extra secret needed).

### VPS Prerequisites

- Docker + Docker Compose installed
- `docker-compose.yml` present at `VPS_DEPLOY_PATH` referencing `ghcr.io/<owner>/obsidian-tasks-notificator:latest`
- `.env` file present alongside `docker-compose.yml` with all required env vars
- SSH public key added to `~/.ssh/authorized_keys` for `VPS_USER`

### Project Layout Addition

```
.github/
└── workflows/
    └── ci-cd.yml
```

---

## Dependencies

- `PyYAML` — frontmatter parsing
- `python-dateutil` — ISO 8601 duration parsing and timezone-aware datetime arithmetic
- `isodate` — ISO 8601 duration parsing (`PT30M` etc.)
- `httpx` or `requests` — Telegram Bot API HTTP calls
- `pytz` — timezone support
- `APScheduler` — in-process cron scheduling (avoids needing `crond` in the container)
