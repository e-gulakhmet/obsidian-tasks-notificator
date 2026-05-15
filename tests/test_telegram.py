import pytest
import httpx
from unittest.mock import patch, MagicMock
from notificator.telegram import send_notification, TelegramError


def _reminder():
    return {"description": "0 minute before", "relatedTo": "scheduled"}


def _task():
    return {
        "title": "My Task",
        "scheduled": None,
        "due": None,
        "file_path": "/vault/tasks/my-task.md",
    }


def test_send_notification_calls_api(respx_mock):
    import respx
    route = respx_mock.post("https://api.telegram.org/bot123:ABC/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    send_notification(
        token="123:ABC",
        chat_id="999",
        reminder=_reminder(),
        task=_task(),
        anchor_value="2026-05-15",
    )
    assert route.called


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
            anchor_value="2026-05-15",
        )
