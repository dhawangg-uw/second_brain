import os
import sys

from loguru import logger

LEVEL_LABELS = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARN",
    "ERROR": "ERR",
}
FILE_LOG_RETENTION = "7 days"


def _compact_log_format(record):
    """Return the compact display format for a Loguru record.

    Compute the display label locally so formatting leaves both the record's
    native level and its caller-provided ``extra`` metadata unchanged.
    """
    level_label = LEVEL_LABELS.get(record["level"].name, record["level"].name)
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        f"<level>{level_label}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>\n{exception}"
    )


def configure_logging():
    """Configure loguru for console and file logging.

    Removes the default handler and sets up:
    - stderr handler at LOG_LEVEL (default: INFO, configurable via env var)
    - File handler at DEBUG level writing to LOG_FILE (default: app.log)
    """
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log_file = os.environ.get("LOG_FILE", "app.log")
    logger.remove()
    logger.add(sys.stderr, level=log_level, format=_compact_log_format)
    logger.add(
        log_file,
        level="DEBUG",
        format=_compact_log_format,
        rotation="50 KB",
        retention=FILE_LOG_RETENTION,
    )


@logger.catch
def main():
    """Run the application.

    Configures logging and prints a greeting to verify the setup works.
    """
    configure_logging()
    logger.info("Hello from second_brain!")
