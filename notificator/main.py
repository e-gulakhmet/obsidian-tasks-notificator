import logging
from datetime import datetime

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
