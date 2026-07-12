import os
import sys

from loguru import logger

LEVEL_LABELS = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARN",
    "ERROR": "ERR",
}


def _level_label(record):
    """Return the compact display label for a Loguru record."""
    level_name = record["level"].name
    label = LEVEL_LABELS.get(level_name, level_name)
    return label.replace("{", "{{").replace("}", "}}")


def _compact_log_format(record):
    """Return the compact display format for a Loguru record.

    Compute the display label locally so formatting leaves both the record's
    native level and its caller-provided ``extra`` metadata unchanged.
    """
    level_label = _level_label(record)
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        f"<level>{level_label}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>\n{exception}"
    )


def _plain_compact_log_format(record):
    """Return a markup-free compact format for non-terminal sinks."""
    level_label = _level_label(record)
    return (
        "{time:YYYY-MM-DD HH:mm:ss} | "
        f"{level_label} | "
        "{name}:{function}:{line} | {message}\n{exception}"
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
    logger.add(
        sys.stderr,
        level=log_level,
        format=_plain_compact_log_format,
        colorize=False,
        enqueue=False,
    )
    logger.add(
        log_file,
        level="DEBUG",
        format=_plain_compact_log_format,
        colorize=False,
        # Issue #1 requires preserving the established file lifecycle policy.
        rotation="50 KB",
        retention=1,
        enqueue=True,
    )


@logger.catch(reraise=True)
def main():
    """Run the application.

    Configures logging and prints a greeting to verify the setup works.
    """
    try:
        configure_logging()
        logger.info("Hello from second_brain!")
    finally:
        logger.complete()
