import json
import logging
import os
from contextlib import contextmanager
from typing import Any

import fcntl

logger = logging.getLogger(__name__)


@contextmanager
def state_file_lock(state_file: str):
    """Serialize readers/writers that update the shared reminder state."""
    lock_path = state_file + ".lock"
    with open(lock_path, "w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def load_state(state_file: str) -> list[dict[str, Any]]:
    """Load reminders from the JSON state file. Returns [] if file does not exist."""
    if not os.path.exists(state_file):
        return []
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load state file %s: %s", state_file, e)
        return []


def save_state(state_file: str, entries: list[dict[str, Any]]) -> None:
    """Atomically write entries to the JSON state file via a tmp file rename."""
    tmp_path = state_file + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, default=str)
        os.replace(tmp_path, state_file)
    except Exception as e:
        logger.error("Failed to save state file %s: %s", state_file, e)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def merge_reminders(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge incoming reminders into existing state.
    - Entries in incoming not in existing are added.
    - Entries in existing not in incoming are removed.
    - sent_at from existing is preserved over incoming's null.
    """
    existing_by_id = {e["id"]: e for e in existing}
    result = []
    for entry in incoming:
        eid = entry["id"]
        if eid in existing_by_id and existing_by_id[eid].get("sent_at") is not None:
            merged = dict(entry)
            merged["sent_at"] = existing_by_id[eid]["sent_at"]
            result.append(merged)
        else:
            result.append(dict(entry))
    return result
