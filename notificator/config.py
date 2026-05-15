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
    cron_schedule: str


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
        cron_schedule=os.environ.get("CRON_SCHEDULE", "* * * * *"),
    )
