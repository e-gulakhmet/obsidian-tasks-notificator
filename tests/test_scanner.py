import pytest
from pathlib import Path
from datetime import date
from notificator.scanner import scan_tasks, _to_date, _to_iso_str

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


def test_task_has_new_fields():
    today = date(2026, 5, 15)
    tasks = scan_tasks(str(FIXTURES), today)
    task = next(t for t in tasks if t["title"] == "Today Task")
    assert task["priority"] == "high"
    assert task["projects"] == ["Work", "Home"]
    assert task["contexts"] == ["@office"]
    assert task["time_estimate"] == 30
    assert task["recurrence"] == "weekly"


def test_task_projects_normalised_to_list_when_string(tmp_path):
    """A scalar projects value should be normalised to a list."""
    md = tmp_path / "single_project.md"
    md.write_text("---\ntitle: T\nstatus: todo\nscheduled: 2026-05-15\nprojects: Solo\n---\n")
    tasks = scan_tasks(str(tmp_path), date(2026, 5, 15))
    assert tasks[0]["projects"] == ["Solo"]


def test_task_missing_optional_fields_default_to_empty(tmp_path):
    """Tasks without optional fields get safe defaults."""
    md = tmp_path / "minimal.md"
    md.write_text("---\ntitle: M\nstatus: todo\nscheduled: 2026-05-15\n---\n")
    tasks = scan_tasks(str(tmp_path), date(2026, 5, 15))
    t = tasks[0]
    assert t["priority"] is None
    assert t["projects"] == []
    assert t["contexts"] == []
    assert t["time_estimate"] is None
    assert t["recurrence"] is None


# --- _to_date unit tests ---

def test_to_date_from_date_object():
    from datetime import date as d
    assert _to_date(d(2026, 5, 16)) == d(2026, 5, 16)


def test_to_date_from_datetime_object():
    from datetime import datetime
    assert _to_date(datetime(2026, 5, 16, 13, 0)) == date(2026, 5, 16)


def test_to_date_from_date_string():
    assert _to_date("2026-05-16") == date(2026, 5, 16)


def test_to_date_from_datetime_string_no_seconds():
    assert _to_date("2026-05-16T13:00") == date(2026, 5, 16)


def test_to_date_from_datetime_string_with_seconds():
    assert _to_date("2026-05-16T13:00:00") == date(2026, 5, 16)


def test_to_date_invalid_returns_none():
    assert _to_date("not-a-date") is None


def test_to_date_none_returns_none():
    assert _to_date(None) is None


def test_scan_includes_task_with_datetime_scheduled():
    """Task with scheduled: 2026-05-15T09:00 (no seconds) must be included."""
    today = date(2026, 5, 15)
    tasks = scan_tasks(str(FIXTURES), today)
    titles = [t["title"] for t in tasks]
    assert "Datetime Scheduled Task" in titles


def test_scan_datetime_scheduled_preserves_time():
    """scheduled: 2026-05-15T09:00 stored as ISO string with time component."""
    today = date(2026, 5, 15)
    tasks = scan_tasks(str(FIXTURES), today)
    task = next(t for t in tasks if t["title"] == "Datetime Scheduled Task")
    assert task["scheduled"] == "2026-05-15T09:00"


def test_scan_date_scheduled_stored_as_date_string():
    """scheduled: 2026-05-15 (date-only) stored as date-only ISO string."""
    today = date(2026, 5, 15)
    tasks = scan_tasks(str(FIXTURES), today)
    task = next(t for t in tasks if t["title"] == "Today Task")
    assert task["scheduled"] == "2026-05-15"


# --- _to_iso_str unit tests ---

def test_to_iso_str_date_object():
    assert _to_iso_str(date(2026, 5, 16)) == "2026-05-16"


def test_to_iso_str_datetime_object_no_seconds():
    from datetime import datetime
    assert _to_iso_str(datetime(2026, 5, 16, 13, 0)) == "2026-05-16T13:00"


def test_to_iso_str_datetime_object_with_seconds():
    from datetime import datetime
    assert _to_iso_str(datetime(2026, 5, 16, 13, 0, 30)) == "2026-05-16T13:00:30"


def test_to_iso_str_date_string():
    assert _to_iso_str("2026-05-16") == "2026-05-16"


def test_to_iso_str_datetime_string_no_seconds():
    assert _to_iso_str("2026-05-16T13:00") == "2026-05-16T13:00"


def test_to_iso_str_datetime_string_with_zero_seconds():
    assert _to_iso_str("2026-05-16T13:00:00") == "2026-05-16T13:00"


def test_to_iso_str_none_returns_none():
    assert _to_iso_str(None) is None
