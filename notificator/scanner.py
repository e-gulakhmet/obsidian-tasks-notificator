import glob
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _to_date(val: Any) -> date | None:
    """Convert a YAML-parsed value to a date object."""
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return datetime.strptime(val, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _read_frontmatter(path: str) -> dict[str, Any] | None:
    """Read only the YAML frontmatter from a .md file (stops at closing ---)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline()
            if first_line.strip() != "---":
                return None
            lines = []
            for line in f:
                if line.strip() == "---":
                    break
                lines.append(line)
        return yaml.safe_load("".join(lines)) or {}
    except Exception as e:
        logger.warning("Failed to read frontmatter from %s: %s", path, e)
        return None


def scan_tasks(tasks_dir: str, today: date) -> list[dict[str, Any]]:
    """Return task dicts for non-done tasks scheduled or due today."""
    results = []
    pattern = str(Path(tasks_dir) / "*.md")
    for path in glob.glob(pattern):
        fm = _read_frontmatter(path)
        if fm is None:
            continue
        if fm.get("status") == "done":
            continue
        scheduled = fm.get("scheduled")
        due = fm.get("due")

        scheduled_date = _to_date(scheduled)
        due_date = _to_date(due)

        if scheduled_date != today and due_date != today:
            continue

        results.append({
            "title": fm.get("title", Path(path).stem),
            "status": fm.get("status"),
            "scheduled": scheduled_date,
            "due": due_date,
            "reminders": fm.get("reminders") or [],
            "file_path": path,
        })
    return results
