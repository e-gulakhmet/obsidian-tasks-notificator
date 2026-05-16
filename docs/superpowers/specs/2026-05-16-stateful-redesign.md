# Stateful Redesign: Two-Job Architecture

**Date:** 2026-05-16  
**Status:** Approved

## Overview

Replace the stateless single-pass loop with two decoupled APScheduler jobs running in one process. A **scanner job** reads Obsidian task files and writes pending reminders to a JSON state file. A **sender job** reads the state file, sends due Telegram notifications, and marks them sent.

## Architecture

```
[TASKS_DIR]  ──scan──>  [reminders.json]  ──send──>  [Telegram]
   .md files              /data volume              Bot API
```

One container, one Python process, two jobs sharing `/data/reminders.json` on a Docker volume.

## Scheduling

- `SCANNER_CRON` env var — cron expression for the scanner job (e.g. `0 0 * * *` for daily at midnight)
- `SENDER_CRON` env var — cron expression for the sender job (e.g. `* * * * *` for every minute)
- Both default values must be documented in `.env.example`
- APScheduler `CronTrigger` used for both jobs

## State File

**Location:** `STATE_FILE` env var, default `/data/reminders.json`. `/data` mounted as a Docker volume.

**Schema** — JSON array of reminder objects:

```json
[
  {
    "id": "tasks/my-task.md::0",
    "file": "tasks/my-task.md",
    "title": "My Task",
    "description": "30 min before",
    "fire_time": "2026-05-16T09:30:00+00:00",
    "sent_at": null
  }
]
```

- `id`: `<relative_file_path>::<reminder_index>` — stable identifier for merge deduplication
- `fire_time`: ISO 8601 datetime string (UTC)
- `sent_at`: ISO 8601 datetime string when sent, `null` when pending

## Scanner Job (`scan_job`)

1. Call existing `scan_tasks()` to get today's non-done tasks with reminders
2. Call existing `compute_fire_time()` for each reminder to get `fire_time`
3. Load current state file (`load_state()`)
4. Merge: add new reminder entries, preserve `sent_at` on existing ones, remove entries no longer present
5. Save updated state (`save_state()` — atomic write via tmp file rename)

Errors on individual files are logged and skipped; the job does not crash.

## Sender Job (`send_job`)

1. Load current state file (`load_state()`)
2. Find entries where `fire_time <= now` and `sent_at is null`
3. For each due reminder, call existing `send_notification()`
4. On success, write `sent_at = now` back to state and save
5. On Telegram failure, log error; do NOT write `sent_at` — reminder retries on next run

## Components

| Module | Change |
|---|---|
| `notificator/config.py` | Add `STATE_FILE`, `SCANNER_CRON`, `SENDER_CRON` |
| `notificator/scanner.py` | Unchanged |
| `notificator/reminder.py` | Unchanged |
| `notificator/telegram.py` | Unchanged |
| `notificator/state.py` | **New** — `load_state()`, `save_state()`, `merge_reminders()` |
| `notificator/jobs.py` | **New** — `scan_job()`, `send_job()` |
| `notificator/main.py` | Replace `run_once()` with two APScheduler job registrations |

## Error Handling

- Scanner: file read/parse errors → log + skip, job continues
- Sender: Telegram API error → log + skip reminder, `sent_at` not written (will retry)
- State file write: atomic rename (`reminders.json.tmp` → `reminders.json`) to prevent corruption
- Missing state file on startup: treated as empty state (no error)

## Testing

- `notificator/state.py`: unit tests for `load_state`, `save_state`, `merge_reminders` (new + existing + removed + sent preservation)
- `notificator/jobs.py`: integration tests with temp directory and mocked Telegram
- All existing 16 tests must remain green
- `docker-compose.yml`: add `/data` volume mount

## Environment Variables (additions)

| Variable | Default | Description |
|---|---|---|
| `STATE_FILE` | `/data/reminders.json` | Path to JSON state file |
| `SCANNER_CRON` | `0 0 * * *` | Cron schedule for scanner job |
| `SENDER_CRON` | `* * * * *` | Cron schedule for sender job |
