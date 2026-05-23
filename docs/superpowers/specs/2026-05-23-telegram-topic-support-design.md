# Telegram Topic Support Design

**Date:** 2026-05-23  
**Status:** Approved

## Overview

Add optional support for sending notifications to a specific Telegram topic (forum thread) within a supergroup. Configured globally via a single env var. If not set, notifications go to the General topic (existing behavior, no breaking change).

## Architecture

No new components. Three small changes to existing modules:

- `config.py` — add one optional field
- `telegram.py` — add one optional parameter to `send_notification`
- `jobs.py` — pass the new config field to `send_notification`

## Config

New optional field added to `Config`:

```python
telegram_topic_id: str | None  # loaded from TELEGRAM_TOPIC_ID env var, default None
```

Loaded with `os.environ.get("TELEGRAM_TOPIC_ID")` — no error if absent.

## Telegram API

The Bot API `sendMessage` endpoint accepts an optional `message_thread_id` integer parameter. When present, the message is sent to that topic. When absent, the message goes to the General topic.

`send_notification` signature change:

```python
def send_notification(token, chat_id, reminder, task, topic_id=None)
```

Payload:
```python
payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
if topic_id:
    payload["message_thread_id"] = int(topic_id)
```

## Jobs

`send_job` passes `config.telegram_topic_id` to `send_notification`:

```python
send_notification(
    token=config.telegram_token,
    chat_id=config.telegram_chat_id,
    reminder=reminder,
    task=task,
    topic_id=config.telegram_topic_id,
)
```

## CI/CD

`ci-cd.yml` deploy script updated to include `TELEGRAM_TOPIC_ID` in the `.env` written to VPS (written as empty string if secret not set — harmless, `os.environ.get` returns `None` for empty strings after strip).

`TELEGRAM_TOPIC_ID` added as optional GitHub Actions secret.

## Testing

Two new tests in `test_telegram.py`:

- `test_send_notification_includes_message_thread_id_when_topic_set` — verifies `message_thread_id` present in API payload
- `test_send_notification_no_message_thread_id_when_topic_not_set` — verifies `message_thread_id` absent from payload

## Constraints

- `telegram_topic_id` stored as `str | None`; converted to `int` at send time (Telegram API requires integer)
- Empty string treated as `None` (no topic) — `if topic_id:` handles this
- No schema changes to state file
- No changes to scanner or reminder logic
