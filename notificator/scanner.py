import glob
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _to_date(val: Any) -> date | None:
    """Convert a YAML-parsed value to a date object.

    Handles:
    - datetime.date or datetime.datetime objects (PyYAML may produce either)
    - ISO 8601 date strings: "2026-05-16"
    - ISO 8601 datetime strings without seconds: "2026-05-16T13:00"
    - ISO 8601 datetime strings with seconds: "2026-05-16T13:00:00"
    """
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
        return None
    return None

def _to_iso_str(val: Any) -> str | None:
    """Return a canonical ISO string preserving time component if present.

    - date object         -> "2026-05-16"
    - datetime object     -> "2026-05-16T13:00"  (no seconds unless non-zero)
    - "2026-05-16"        -> "2026-05-16"
    - "2026-05-16T13:00"  -> "2026-05-16T13:00"  (kept as-is)
    - "2026-05-16T13:00:00" -> "2026-05-16T13:00" (seconds stripped when zero)
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.second == 0 and val.microsecond == 0:
            return val.strftime("%Y-%m-%dT%H:%M")
        return val.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, str):
        # Try datetime formats first (with T), then date-only
        for fmt, has_time in (
            ("%Y-%m-%dT%H:%M:%S", True),
            ("%Y-%m-%dT%H:%M", True),
            ("%Y-%m-%d", False),
        ):
            try:
                dt = datetime.strptime(val, fmt)
                if has_time:
                    if dt.second == 0 and dt.microsecond == 0:
                        return dt.strftime("%Y-%m-%dT%H:%M")
                    return dt.strftime("%Y-%m-%dT%H:%M:%S")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
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

        # Normalise list-or-string fields to list
        def _to_list(val: Any) -> list[str]:
            if not val:
                return []
            if isinstance(val, list):
                return [str(v) for v in val]
            return [str(val)]

        results.append(
            {
                "title": fm.get("title", Path(path).stem),
                "status": fm.get("status"),
                "priority": fm.get("priority"),
                "scheduled": _to_iso_str(scheduled),
                "due": _to_iso_str(due),
                "projects": _to_list(fm.get("projects")),
                "contexts": _to_list(fm.get("contexts")),
                "time_estimate": fm.get("timeEstimate"),
                "recurrence": fm.get("recurrence"),
                "reminders": fm.get("reminders") or [],
                "file_path": path,
                # internal: used only for reminder computation, not stored in state
                "_scheduled_date": scheduled_date,
                "_due_date": due_date,
            }
        )
    return results
