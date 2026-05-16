import os
from dataclasses import dataclass


class ConfigError(Exception):
    pass


@dataclass
class Config:
    tasks_dir: str
    telegram_token: str
    telegram_chat_id: str
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
        timezone=require("TIMEZONE"),
        state_file=os.environ.get("STATE_FILE", "/data/reminders.json"),
        scanner_cron=os.environ.get("SCANNER_CRON", "*/10 * * * *"),
        sender_cron=os.environ.get("SENDER_CRON", "* * * * *"),
    )
