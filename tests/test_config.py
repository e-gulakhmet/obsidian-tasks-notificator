import os
import pytest
from notificator.config import ConfigError, load_config


def test_load_config_all_required(monkeypatch):
    monkeypatch.setenv("TASKS_DIR", "/vault/tasks")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.delenv("STATE_FILE", raising=False)
    monkeypatch.delenv("SCANNER_CRON", raising=False)
    monkeypatch.delenv("SENDER_CRON", raising=False)

    config = load_config()

    assert config.tasks_dir == "/vault/tasks"
    assert config.telegram_token == "tok"
    assert config.telegram_chat_id == "123"
    assert config.timezone == "UTC"
    assert config.state_file == "/data/reminders.json"
    assert config.scanner_cron == "*/10 * * * *"
    assert config.sender_cron == "* * * * *"


def test_load_config_custom_optional(monkeypatch):
    monkeypatch.setenv("TASKS_DIR", "/vault/tasks")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("STATE_FILE", "/tmp/state.json")
    monkeypatch.setenv("SCANNER_CRON", "0 6 * * *")
    monkeypatch.setenv("SENDER_CRON", "*/5 * * * *")

    config = load_config()

    assert config.state_file == "/tmp/state.json"
    assert config.scanner_cron == "0 6 * * *"
    assert config.sender_cron == "*/5 * * * *"


def test_load_config_missing_required(monkeypatch):
    monkeypatch.delenv("TASKS_DIR", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TIMEZONE", "UTC")

    with pytest.raises(ConfigError, match="TASKS_DIR"):
        load_config()
