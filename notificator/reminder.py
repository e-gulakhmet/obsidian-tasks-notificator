import logging
from datetime import date, datetime, timezone
from typing import Any

import isodate
import pytz

logger = logging.getLogger(__name__)


class ReminderError(Exception):
    pass


def has_time_component(value: Any) -> bool:
    """Return True when a scheduled value includes an explicit time."""
    if isinstance(value, datetime):
        return True
    if isinstance(value, date):
        return False
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                datetime.strptime(value, fmt)
                return True
            except ValueError:
                continue
    return False


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
        if anchor_field == "scheduled" and not has_time_component(anchor_value):
            raise ReminderError(
                f"Anchor field '{anchor_field}' for task '{task.get('title')}' has no time component"
            )

        # Normalize anchor to a timezone-aware datetime
        if isinstance(anchor_value, datetime):
            if anchor_value.tzinfo is None:
                anchor_dt = tz.localize(anchor_value)
            else:
                anchor_dt = anchor_value.astimezone(tz)
        elif isinstance(anchor_value, date):
            anchor_dt = tz.localize(datetime(anchor_value.year, anchor_value.month, anchor_value.day))
        elif isinstance(anchor_value, str):
            parsed = None
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(anchor_value, fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                raise ReminderError(
                    f"Cannot parse anchor field '{anchor_field}' value '{anchor_value}' as date/datetime"
                )
            anchor_dt = tz.localize(parsed)
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
