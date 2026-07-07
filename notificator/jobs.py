import logging
from datetime import datetime, timezone
from typing import Any

import pytz

from notificator.config import Config
from notificator.reminder import compute_fire_time, has_time_component, ReminderError
from notificator.scanner import scan_tasks
from notificator.state import load_state, merge_reminders, save_state, state_file_lock
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
        if not has_time_component(task.get("scheduled")):
            logger.info(
                "scan_job: skipping task '%s' because scheduled has no time component",
                task.get("title"),
            )
            continue
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
                "status": task.get("status"),
                "priority": task.get("priority"),
                "scheduled": task.get("scheduled"),
                "due": task.get("due"),
                "projects": task.get("projects", []),
                "contexts": task.get("contexts", []),
                "time_estimate": task.get("time_estimate"),
                "recurrence": task.get("recurrence"),
                "description": reminder.get("description", ""),
                "reminder_type": reminder.get("type"),
                "offset": reminder.get("offset"),
                "fire_time": fire_time.astimezone(timezone.utc).isoformat(),
                "sent_at": None,
            })

    with state_file_lock(config.state_file):
        existing = load_state(config.state_file)
        merged = merge_reminders(existing, incoming)
        save_state(config.state_file, merged)
    logger.info("scan_job: state file updated with %d reminder(s)", len(merged))


def send_job(config: Config) -> None:
    """Send due reminders and mark them sent in the state file."""
    now = datetime.now(timezone.utc)
    with state_file_lock(config.state_file):
        entries = load_state(config.state_file)

        for entry in entries:
            if entry.get("sent_at") is not None:
                continue
            fire_time = datetime.fromisoformat(entry["fire_time"])
            if fire_time.tzinfo is None:
                fire_time = fire_time.replace(tzinfo=timezone.utc)
            if fire_time > now:
                continue

            reminder = {"description": entry.get("description", ""), "id": entry["id"]}
            tz = pytz.timezone(config.timezone)
            fire_dt = fire_time.astimezone(tz)
            reminder["reminder_type"] = entry.get("reminder_type")
            reminder["offset"] = entry.get("offset")
            reminder["fire_time_local"] = fire_dt.strftime("%-d %b %Y, %H:%M")
            task = {
                "title": entry.get("title", ""),
                "file_path": entry.get("file", ""),
                "status": entry.get("status"),
                "priority": entry.get("priority"),
                "scheduled": entry.get("scheduled"),
                "due": entry.get("due"),
                "projects": entry.get("projects", []),
                "contexts": entry.get("contexts", []),
                "time_estimate": entry.get("time_estimate"),
                "recurrence": entry.get("recurrence"),
            }

            try:
                send_notification(
                    token=config.telegram_token,
                    chat_id=config.telegram_chat_id,
                    reminder=reminder,
                    task=task,
                    topic_id=config.telegram_topic_id,
                )
            except TelegramError as e:
                logger.error("send_job: failed to send reminder '%s': %s", entry["id"], e)
                continue
            except Exception:
                logger.exception("send_job: failed to send reminder '%s'", entry["id"])
                continue

            entry["sent_at"] = now.isoformat()
            save_state(config.state_file, entries)
            logger.info("send_job: sent reminder '%s'", entry["id"])
