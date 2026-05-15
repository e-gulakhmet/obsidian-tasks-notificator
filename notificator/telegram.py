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
