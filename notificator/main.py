import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from notificator.config import ConfigError, load_config
from notificator.jobs import scan_job, send_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        config = load_config()
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        raise SystemExit(1)

    logger.info("Starting notificator")
    logger.info("  scanner_cron : %s", config.scanner_cron)
    logger.info("  sender_cron  : %s", config.sender_cron)
    logger.info("  state_file   : %s", config.state_file)

    scheduler = BlockingScheduler(timezone=config.timezone)

    scheduler.add_job(
        scan_job,
        CronTrigger.from_crontab(config.scanner_cron, timezone=config.timezone),
        args=[config],
        id="scan_job",
        name="Scanner",
    )
    scheduler.add_job(
        send_job,
        CronTrigger.from_crontab(config.sender_cron, timezone=config.timezone),
        args=[config],
        id="send_job",
        name="Sender",
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Notificator stopped.")


if __name__ == "__main__":
    main()
