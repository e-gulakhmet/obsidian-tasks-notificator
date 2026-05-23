# Telegram Topic Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional `TELEGRAM_TOPIC_ID` env var so all notifications are sent to a specific Telegram supergroup topic (forum thread).

**Architecture:** Add `telegram_topic_id: str | None` to `Config`, pass it through `jobs.py` to `send_notification()`, which conditionally includes `message_thread_id` in the Telegram API payload. Update CI/CD deploy script to write the new var to `.env` on the VPS.

**Tech Stack:** Python 3.12, httpx, pytest, GitHub Actions

---

### Task 1: Add `telegram_topic_id` to Config

**Files:**
- Modify: `notificator/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_load_config_topic_id_optional(monkeypatch):
    """TELEGRAM_TOPIC_ID is optional — defaults to None when absent."""
    monkeypatch.setenv("TASKS_DIR", "/tasks")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.delenv("TELEGRAM_TOPIC_ID", raising=False)
    config = load_config()
    assert config.telegram_topic_id is None


def test_load_config_topic_id_set(monkeypatch):
    """TELEGRAM_TOPIC_ID is loaded when present."""
    monkeypatch.setenv("TASKS_DIR", "/tasks")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("TELEGRAM_TOPIC_ID", "456")
    config = load_config()
    assert config.telegram_topic_id == "456"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py::test_load_config_topic_id_optional tests/test_config.py::test_load_config_topic_id_set -v
```

Expected: FAIL — `Config` has no field `telegram_topic_id`

- [ ] **Step 3: Implement the change**

Replace `notificator/config.py` with:

```python
import os
from dataclasses import dataclass


class ConfigError(Exception):
    pass


@dataclass
class Config:
    tasks_dir: str
    telegram_token: str
    telegram_chat_id: str
    telegram_topic_id: str | None
    timezone: str
    state_file: str
    scanner_cron: str
    sender_cron: str


def load_config() -> Config:
    def require(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise ConfigError(f"Required environment variable '{name}' is missing or empty.")
        return value

    return Config(
        tasks_dir=require("TASKS_DIR"),
        telegram_token=require("TELEGRAM_TOKEN"),
        telegram_chat_id=require("TELEGRAM_CHAT_ID"),
        telegram_topic_id=os.environ.get("TELEGRAM_TOPIC_ID") or None,
        timezone=require("TIMEZONE"),
        state_file=os.environ.get("STATE_FILE", "/data/reminders.json"),
        scanner_cron=os.environ.get("SCANNER_CRON", "*/10 * * * *"),
        sender_cron=os.environ.get("SENDER_CRON", "* * * * *"),
    )
```

Note: `os.environ.get("TELEGRAM_TOPIC_ID") or None` ensures an empty string `""` is also treated as `None`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add notificator/config.py tests/test_config.py
git commit -m "feat: add optional telegram_topic_id to Config"
```

---

### Task 2: Add `topic_id` parameter to `send_notification`

**Files:**
- Modify: `notificator/telegram.py`
- Test: `tests/test_telegram.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_telegram.py`:

```python
def test_send_notification_includes_message_thread_id_when_topic_set(respx_mock):
    respx_mock.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    reminder = {"id": "r1", "reminder_type": "relative", "offset": "-PT0M", "fire_time_local": "22 May 2026, 19:20"}
    task = {"title": "Test", "file_path": "/tasks/test.md", "status": "open", "priority": None,
            "scheduled": None, "due": None, "projects": [], "contexts": [], "time_estimate": None, "recurrence": None}
    send_notification("TOKEN", "CHAT", reminder, task, topic_id="42")
    request = respx_mock.calls[0].request
    import json
    payload = json.loads(request.content)
    assert payload["message_thread_id"] == 42


def test_send_notification_no_message_thread_id_when_topic_not_set(respx_mock):
    respx_mock.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    reminder = {"id": "r1", "reminder_type": "relative", "offset": "-PT0M", "fire_time_local": "22 May 2026, 19:20"}
    task = {"title": "Test", "file_path": "/tasks/test.md", "status": "open", "priority": None,
            "scheduled": None, "due": None, "projects": [], "contexts": [], "time_estimate": None, "recurrence": None}
    send_notification("TOKEN", "CHAT", reminder, task, topic_id=None)
    request = respx_mock.calls[0].request
    import json
    payload = json.loads(request.content)
    assert "message_thread_id" not in payload
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_telegram.py::test_send_notification_includes_message_thread_id_when_topic_set tests/test_telegram.py::test_send_notification_no_message_thread_id_when_topic_not_set -v
```

Expected: FAIL — `send_notification` does not accept `topic_id`

- [ ] **Step 3: Implement the change**

In `notificator/telegram.py`, replace the `send_notification` function signature and body:

```python
def send_notification(
    token: str,
    chat_id: str,
    reminder: dict[str, Any],
    task: dict[str, Any],
    topic_id: str | None = None,
) -> None:
    """Send a Telegram message for a fired reminder. Raises TelegramError on failure."""
    text = _format_message(reminder, task)
    url = TELEGRAM_API.format(token=token)
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if topic_id:
        payload["message_thread_id"] = int(topic_id)
    response = httpx.post(url, json=payload)
    if not response.is_success:
        raise TelegramError(
            f"Telegram API returned {response.status_code}: {response.text}"
        )
    logger.info("Notification sent for task '%s', reminder '%s'", task.get("title"), reminder.get("id"))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_telegram.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add notificator/telegram.py tests/test_telegram.py
git commit -m "feat: pass message_thread_id to Telegram API when topic_id is set"
```

---

### Task 3: Pass `topic_id` from config through `send_job`

**Files:**
- Modify: `notificator/jobs.py`
- Test: `tests/test_jobs.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_jobs.py`:

```python
def test_send_job_passes_topic_id_to_send_notification(tmp_path, monkeypatch):
    """send_job passes config.telegram_topic_id to send_notification."""
    import json
    from datetime import datetime, timezone, timedelta
    from notificator.jobs import send_job
    from notificator.config import Config

    state = [{
        "id": "f::0",
        "file": str(tmp_path / "t.md"),
        "title": "T",
        "status": "open",
        "priority": None,
        "scheduled": None,
        "due": None,
        "projects": [],
        "contexts": [],
        "time_estimate": None,
        "recurrence": None,
        "description": "",
        "reminder_type": "relative",
        "offset": "-PT0M",
        "fire_time": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        "sent_at": None,
    }]
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state))

    config = Config(
        tasks_dir=str(tmp_path),
        telegram_token="tok",
        telegram_chat_id="chat",
        telegram_topic_id="99",
        timezone="UTC",
        state_file=str(state_file),
        scanner_cron="*/10 * * * *",
        sender_cron="* * * * *",
    )

    calls = []
    monkeypatch.setattr(
        "notificator.jobs.send_notification",
        lambda **kwargs: calls.append(kwargs),
    )
    send_job(config)
    assert calls[0]["topic_id"] == "99"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_jobs.py::test_send_job_passes_topic_id_to_send_notification -v
```

Expected: FAIL — `send_notification` call in `send_job` doesn't pass `topic_id`

- [ ] **Step 3: Implement the change**

In `notificator/jobs.py`, update the `send_notification` call in `send_job`:

```python
        try:
            send_notification(
                token=config.telegram_token,
                chat_id=config.telegram_chat_id,
                reminder=reminder,
                task=task,
                topic_id=config.telegram_topic_id,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_jobs.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add notificator/jobs.py tests/test_jobs.py
git commit -m "feat: pass telegram_topic_id from config to send_notification in send_job"
```

---

### Task 4: Update CI/CD deploy script and `.env.example`

**Files:**
- Modify: `.github/workflows/ci-cd.yml`
- Modify: `.env.example`

- [ ] **Step 1: Update `.env.example`**

Add the following line to `.env.example` (after `TELEGRAM_CHAT_ID`):

```
# Optional: Telegram supergroup topic (forum thread) ID. If set, all notifications go to this topic.
TELEGRAM_TOPIC_ID=
```

- [ ] **Step 2: Update `ci-cd.yml` deploy script**

In `.github/workflows/ci-cd.yml`, update the `env:` block under the deploy step to add:

```yaml
          TELEGRAM_TOPIC_ID: ${{ secrets.TELEGRAM_TOPIC_ID }}
```

Update the `envs:` line to include it:

```yaml
          envs: TASKS_DIR,TASKS_DIR_HOST,TELEGRAM_TOKEN,TELEGRAM_CHAT_ID,TELEGRAM_TOPIC_ID,TIMEZONE,STATE_FILE,SCANNER_CRON,SENDER_CRON
```

Update the `printf` in the script to include it:

```bash
            printf 'TASKS_DIR=%s\nTASKS_DIR_HOST=%s\nTELEGRAM_TOKEN=%s\nTELEGRAM_CHAT_ID=%s\nTELEGRAM_TOPIC_ID=%s\nTIMEZONE=%s\nSTATE_FILE=%s\nSCANNER_CRON=%s\nSENDER_CRON=%s\n' \
              "$TASKS_DIR" "$TASKS_DIR_HOST" "$TELEGRAM_TOKEN" "$TELEGRAM_CHAT_ID" "$TELEGRAM_TOPIC_ID" \
              "$TIMEZONE" "$STATE_FILE" "$SCANNER_CRON" "$SENDER_CRON" > .env
```

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: All PASS (90+ tests)

- [ ] **Step 4: Commit and push**

```bash
git add .env.example .github/workflows/ci-cd.yml
git commit -m "feat: include TELEGRAM_TOPIC_ID in deploy .env and document in .env.example"
git push
```

- [ ] **Step 5: Set GitHub Actions secret (manual)**

```bash
gh secret set TELEGRAM_TOPIC_ID --body "<your_topic_id>"
```

If not using topics yet, skip this step — the secret absence results in an empty string which is treated as `None`.
