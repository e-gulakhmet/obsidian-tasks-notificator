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
    task = _task(scheduled=datetime(2026, 5, 15, 9, 0))
    reminder = {
        "id": "rem_1",
        "type": "relative",
        "description": "0 minute before",
        "relatedTo": "scheduled",
        "offset": "-PT0M",
    }
    fire = compute_fire_time(reminder, task, TZ)
    expected = TZ.localize(datetime(2026, 5, 15, 9, 0, 0))
    assert fire == expected


def test_relative_30min_before_scheduled():
    task = _task(scheduled="2026-05-15T09:00")
    reminder = {
        "id": "rem_2",
        "type": "relative",
        "description": "30 minutes before",
        "relatedTo": "scheduled",
        "offset": "-PT30M",
    }
    fire = compute_fire_time(reminder, task, TZ)
    expected = TZ.localize(datetime(2026, 5, 15, 8, 30, 0))
    assert fire == expected


def test_relative_scheduled_without_time_raises():
    task = _task(scheduled=date(2026, 5, 15))
    reminder = {
        "id": "rem_2",
        "type": "relative",
        "description": "30 minutes before",
        "relatedTo": "scheduled",
        "offset": "-PT30M",
    }
    with pytest.raises(ReminderError, match="scheduled.*no time component"):
        compute_fire_time(reminder, task, TZ)


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
