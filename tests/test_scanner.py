import pytest
from pathlib import Path
from datetime import date
from notificator.scanner import scan_tasks

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
