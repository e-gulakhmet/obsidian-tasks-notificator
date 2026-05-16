import json
import pytest
import httpx
from notificator.telegram import send_notification, TelegramError, _format_message, _format_date_str, _offset_label


def _reminder(**overrides):
    base = {"description": "0 minute before", "id": "some::0"}
    base.update(overrides)
    return base


def _task(**overrides):
    base = {
        "title": "My Task",
        "status": "todo",
        "priority": "high",
        "scheduled": "2026-05-15",
        "due": "2026-05-16",
        "projects": ["Work", "Home"],
        "contexts": ["@office"],
        "time_estimate": 30,
        "recurrence": "weekly",
        "file_path": "/vault/tasks/my-task.md",
    }
    base.update(overrides)
    return base


# --- _format_date_str unit tests ---

def test_format_date_str_date_only():
    assert _format_date_str("2026-05-16") == "16 May 2026"


def test_format_date_str_datetime_no_seconds():
    assert _format_date_str("2026-05-16T13:00") == "16 May 2026, 13:00"


def test_format_date_str_datetime_with_seconds():
    assert _format_date_str("2026-05-16T13:00:00") == "16 May 2026, 13:00"


def test_format_date_str_none_returns_none():
    assert _format_date_str(None) is None


# --- _offset_label unit tests ---

def test_offset_label_zero():
    assert _offset_label("relative", "-PT0M", None) == "(now)"


def test_offset_label_zero_seconds():
    assert _offset_label("relative", "PT0S", None) == "(now)"


def test_offset_label_10_minutes():
    assert _offset_label("relative", "-PT10M", None) == "(in 10 min)"


def test_offset_label_1_hour():
    assert _offset_label("relative", "-PT1H", None) == "(in 1 hour)"


def test_offset_label_2_hours():
    assert _offset_label("relative", "-PT2H", None) == "(in 2 hours)"


def test_offset_label_90_minutes():
    assert _offset_label("relative", "-PT90M", None) == "(in 1 hour 30 min)"


def test_offset_label_1_day():
    assert _offset_label("relative", "-P1D", None) == "(in 1 day)"


def test_offset_label_7_days():
    assert _offset_label("relative", "-P7D", None) == "(in 1 week)"


def test_offset_label_positive_after():
    assert _offset_label("relative", "PT30M", None) == "(30 min after)"


def test_offset_label_absolute_uses_fire_time():
    assert _offset_label("absolute", None, "16 May 2026, 13:00") == "(at 16 May 2026, 13:00)"


def test_offset_label_no_offset_falls_back_to_fire_time():
    assert _offset_label("relative", None, "16 May 2026, 13:00") == "(at 16 May 2026, 13:00)"


# --- _format_message unit tests ---

def test_format_title_includes_offset_label():
    r = _reminder(reminder_type="relative", offset="-PT10M")
    msg = _format_message(r, _task())
    assert "<b>My Task (in 10 min)</b>" in msg


def test_format_title_now():
    r = _reminder(reminder_type="relative", offset="-PT0M")
    msg = _format_message(r, _task())
    assert "<b>My Task (now)</b>" in msg


def test_format_title_absolute():
    r = _reminder(reminder_type="absolute", offset=None, fire_time_local="16 May 2026, 13:00")
    msg = _format_message(r, _task())
    assert "<b>My Task (at 16 May 2026, 13:00)</b>" in msg


def test_format_title_no_description_block():
    r = _reminder(reminder_type="relative", offset="-PT10M")
    msg = _format_message(r, _task())
    assert "<i>" not in msg
    assert "📝" not in msg


def test_format_title_no_label_when_no_offset_or_fire_time():
    r = _reminder()  # no reminder_type, no offset, no fire_time_local
    msg = _format_message(r, _task())
    assert "<b>My Task</b>" in msg


def test_format_includes_status():
    msg = _format_message(_reminder(), _task())
    assert "Status: todo" in msg


def test_format_includes_priority():
    msg = _format_message(_reminder(), _task())
    assert "Priority: high" in msg


def test_format_includes_scheduled_date_only():
    msg = _format_message(_reminder(), _task(scheduled="2026-05-15"))
    assert "Scheduled: 15 May 2026" in msg


def test_format_includes_scheduled_datetime():
    msg = _format_message(_reminder(), _task(scheduled="2026-05-15T09:00"))
    assert "Scheduled: 15 May 2026, 09:00" in msg


def test_format_includes_due_date_only():
    msg = _format_message(_reminder(), _task(due="2026-05-16"))
    assert "Due: 16 May 2026" in msg


def test_format_includes_due_datetime():
    msg = _format_message(_reminder(), _task(due="2026-05-16T18:30"))
    assert "Due: 16 May 2026, 18:30" in msg


def test_format_includes_projects():
    msg = _format_message(_reminder(), _task())
    assert "Projects: Work, Home" in msg


def test_format_includes_contexts():
    msg = _format_message(_reminder(), _task())
    assert "Contexts: @office" in msg


def test_format_includes_time_estimate():
    msg = _format_message(_reminder(), _task())
    assert "Estimate: 30 min" in msg


def test_format_includes_recurrence():
    msg = _format_message(_reminder(), _task())
    assert "Recurrence: weekly" in msg


def test_format_no_fire_time_line():
    msg = _format_message(_reminder(), _task())
    assert "🕐" not in msg


def test_format_includes_filename_only():
    msg = _format_message(_reminder(), _task())
    assert "my-task.md" in msg
    assert "/vault/tasks/" not in msg


def test_format_omits_absent_optional_fields():
    t = _task(status=None, priority=None, scheduled=None, due=None,
               projects=[], contexts=[], time_estimate=None, recurrence=None)
    msg = _format_message(_reminder(), t)
    assert "Status" not in msg
    assert "Priority" not in msg
    assert "Scheduled" not in msg
    assert "Due" not in msg
    assert "Projects" not in msg
    assert "Contexts" not in msg
    assert "Estimate" not in msg
    assert "Recurrence" not in msg


def test_format_html_escapes_special_chars():
    t = _task(title="Task <b> & \"fun\"")
    msg = _format_message(_reminder(), t)
    assert "<b>Task &lt;b&gt; &amp; &quot;fun&quot;</b>" in msg


# --- send_notification integration tests ---

def test_send_notification_calls_api(respx_mock):
    route = respx_mock.post("https://api.telegram.org/bot123:ABC/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    send_notification(
        token="123:ABC",
        chat_id="999",
        reminder=_reminder(),
        task=_task(),
    )
    assert route.called


def test_send_notification_uses_html_parse_mode(respx_mock):
    route = respx_mock.post("https://api.telegram.org/bot123:ABC/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    send_notification(
        token="123:ABC",
        chat_id="999",
        reminder=_reminder(),
        task=_task(),
    )
    body = json.loads(route.calls[0].request.content)
    assert body["parse_mode"] == "HTML"


def test_send_notification_raises_on_api_error(respx_mock):
    respx_mock.post("https://api.telegram.org/bot123:ABC/sendMessage").mock(
        return_value=httpx.Response(400, json={"ok": False, "description": "Bad Request"})
    )
    with pytest.raises(TelegramError, match="400"):
        send_notification(
            token="123:ABC",
            chat_id="999",
            reminder=_reminder(),
            task=_task(),
        )
