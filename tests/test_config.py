import pytest
from notificator.config import load_config, ConfigError


def test_load_config_success(monkeypatch):
    monkeypatch.setenv("TASKS_DIR", "/vault/tasks")
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setenv("TIMEZONE", "Europe/Warsaw")

    cfg = load_config()

    assert cfg.tasks_dir == "/vault/tasks"
    assert cfg.telegram_token == "123:ABC"
    assert cfg.telegram_chat_id == "999"
    assert cfg.timezone == "Europe/Warsaw"
    assert cfg.cron_schedule == "* * * * *"  # default


def test_load_config_custom_cron(monkeypatch):
    monkeypatch.setenv("TASKS_DIR", "/vault/tasks")
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("CRON_SCHEDULE", "*/5 * * * *")

    cfg = load_config()

    assert cfg.cron_schedule == "*/5 * * * *"


def test_load_config_missing_required(monkeypatch):
    for key in ("TASKS_DIR", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "TIMEZONE"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigError, match="TASKS_DIR"):
        load_config()
