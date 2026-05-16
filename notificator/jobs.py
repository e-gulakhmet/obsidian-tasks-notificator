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
