import html
import logging
from pathlib import Path
from typing import Any

import httpx
import isodate

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramError(Exception):
    pass


def _format_date_str(val: str | None) -> str | None:
    """Return a human-readable date or datetime string.

    "2026-05-16"       -> "16 May 2026"
    "2026-05-16T13:00" -> "16 May 2026, 13:00"
    """
    if not val:
        return None
    if "T" in val:
        try:
            from datetime import datetime
            dt = datetime.strptime(val, "%Y-%m-%dT%H:%M")
            return dt.strftime("%-d %b %Y, %H:%M")
        except ValueError:
            pass
        try:
            from datetime import datetime
            dt = datetime.strptime(val, "%Y-%m-%dT%H:%M:%S")
            return dt.strftime("%-d %b %Y, %H:%M")
        except ValueError:
            pass
    else:
        try:
            from datetime import datetime
            dt = datetime.strptime(val, "%Y-%m-%d")
            return dt.strftime("%-d %b %Y")
        except ValueError:
            pass
    return val  # fallback: return as-is


def _offset_label(
    reminder_type: str | None,
    offset: str | None,
    fire_time_local: str | None,
) -> str:
    """Return a human-readable label describing when the reminder fires.

    Relative examples:
      "-PT0M"  -> "(now)"
      "-PT10M" -> "(in 10 min)"
      "-PT90M" -> "(in 1 hour 30 min)"
      "-PT2H"  -> "(in 2 hours)"
      "-P1D"   -> "(in 1 day)"
      "-P7D"   -> "(in 1 week)"
      "+PT30M" -> "(30 min after)"

    Absolute example:
      fire_time_local="16 May 2026, 13:00" -> "(at 16 May 2026, 13:00)"
    """
    if reminder_type == "absolute" or not offset:
        if fire_time_local:
            return f"(at {fire_time_local})"
        return ""

    try:
        duration = isodate.parse_duration(offset)
        total_seconds = int(duration.total_seconds())
    except Exception:
        return f"({offset})"

    if total_seconds == 0:
        return "(now)"

    is_before = total_seconds < 0
    secs = abs(total_seconds)

    # Normalise to weeks / days / hours / minutes (ignore sub-minute)
    weeks, secs = divmod(secs, 7 * 24 * 3600)
    days, secs = divmod(secs, 24 * 3600)
    hours, secs = divmod(secs, 3600)
    minutes = secs // 60

    parts: list[str] = []
    if weeks:
        parts.append(f"{weeks} week{'s' if weeks != 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} min")

    if not parts:
        return "(now)"

    label = " ".join(parts)
    if is_before:
        return f"(in {label})"
    return f"({label} after)"


def _format_message(
    reminder: dict[str, Any],
    task: dict[str, Any],
) -> str:
    """Format a Telegram HTML message for a fired reminder."""
    e = html.escape

    lines: list[str] = []

    # Header: title + offset label
    title = str(task.get("title", ""))
    label = _offset_label(
        reminder.get("reminder_type"),
        reminder.get("offset"),
        reminder.get("fire_time_local"),
    )
    header = f"{title} {label}".strip() if label else title
    lines.append(f"🔔 <b>{e(header)}</b>")

    # Task metadata block
    meta: list[str] = []
    if task.get("status"):
        meta.append(f"🏷 Status: {e(str(task['status']))}")
    if task.get("priority"):
        meta.append(f"⚡ Priority: {e(str(task['priority']))}")
    scheduled_str = _format_date_str(task.get("scheduled"))
    if scheduled_str:
        meta.append(f"📅 Scheduled: {e(scheduled_str)}")
    due_str = _format_date_str(task.get("due"))
    if due_str:
        meta.append(f"⏰ Due: {e(due_str)}")
    projects = task.get("projects") or []
    if projects:
        meta.append(f"📁 Projects: {e(', '.join(str(p) for p in projects))}")
    contexts = task.get("contexts") or []
    if contexts:
        meta.append(f"📍 Contexts: {e(', '.join(str(c) for c in contexts))}")
    if task.get("time_estimate"):
        meta.append(f"⏱ Estimate: {e(str(task['time_estimate']))} min")
    if task.get("recurrence"):
        meta.append(f"🔁 Recurrence: {e(str(task['recurrence']))}")

    if meta:
        lines.append("")
        lines.extend(meta)

    # Footer: filename
    lines.append("")
    file_path = task.get("file_path", "")
    lines.append(f"📄 {e(Path(file_path).name)}")

    return "\n".join(lines)


def send_notification(
    token: str,
    chat_id: str,
    reminder: dict[str, Any],
    task: dict[str, Any],
) -> None:
    """Send a Telegram message for a fired reminder. Raises TelegramError on failure."""
    text = _format_message(reminder, task)
    url = TELEGRAM_API.format(token=token)
    response = httpx.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
    )
    if not response.is_success:
        raise TelegramError(
            f"Telegram API returned {response.status_code}: {response.text}"
        )
    logger.info("Notification sent for task '%s', reminder '%s'", task.get("title"), reminder.get("id"))
