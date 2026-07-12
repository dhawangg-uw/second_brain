import os
import sys
from pathlib import Path
from threading import RLock

from loguru import logger

LEVEL_LABELS = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARN",
    "ERROR": "ERR",
}
TRUTHY_ENV_VALUES = {"1", "true", "t", "yes", "y", "on"}
_CONFIGURE_LOCK = RLock()


def _require_loguru_api():
    """Fail clearly when the installed Loguru lacks required queue APIs."""
    missing = [
        name
        for name in ("catch", "complete")
        if not callable(getattr(logger, name, None))
    ]
    if missing:
        names = ", ".join(f"logger.{name}()" for name in missing)
        raise RuntimeError(f"Loguru 0.7.3 or newer is required; missing API: {names}")


def _env_flag(name, *, default=False):
    """Return a case-insensitive boolean flag from the environment."""
    fallback = "true" if default else "false"
    return os.environ.get(name, fallback).strip().lower() in TRUTHY_ENV_VALUES


def _prepare_log_parent(log_file):
    """Create and validate the configured log file's parent directory."""
    parent = Path(log_file).expanduser().parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"Invalid LOG_FILE parent: {parent}") from error
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        raise ValueError(f"LOG_FILE parent is not writable: {parent}")


def _level_label(record):
    """Return a label escaped once for Loguru's returned format template.

    The caller must interpolate this value directly into a callable format's
    template. Passing it through another formatting stage would double-escape
    literal braces in custom level names.
    """
    level = record.get("level")
    level_name = getattr(level, "name", None)
    if level_name is None:
        level_name = "UNKNOWN" if level is None else str(level)
    label = LEVEL_LABELS.get(level_name, level_name)
    return label.replace("{", "{{").replace("}", "}}")


def _compact_log_format(record):
    """Return the compact display format for a Loguru record.

    Compute the display label locally so formatting leaves both the record's
    native level and its caller-provided ``extra`` metadata unchanged.
    Keep this callable at module scope: queued sinks and spawn-based workers
    require the formatter object to remain importable and picklable.
    """
    level_label = _level_label(record)
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        f"<level>{level_label}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>\n{exception}"
    )


def _plain_compact_log_format(record):
    """Return a markup-free, module-level format for queued file sinks.

    Like the colored formatter, this must remain importable and picklable for
    spawn-based multiprocessing.
    """
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

    Both sinks intentionally share the compact field layout required by issue
    #1. Sink-specific behavior belongs in handler options, not separate layouts.
    Stderr writes synchronously so command-line feedback is immediate; queued
    serialization is reserved for the rotating file sink. Concurrent callers
    that require ordered console records should use the file output instead.
    Prefer calling this once during startup. A process-local lock serializes
    concurrent calls so each call snapshots its environment settings and
    replaces both handlers as one configuration transaction.

    Example output::

        2026-07-11 12:34:56 | INFO | second_brain.app:main:99 | Hello
    """
    _require_loguru_api()
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log_file = os.environ.get("LOG_FILE", "app.log")
    console_colorize = _env_flag("LOG_COLORIZE")
    try:
        logger.level(log_level)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid LOG_LEVEL: {log_level!r}") from None
    _prepare_log_parent(log_file)

    with _CONFIGURE_LOCK:
        logger.remove()
        try:
            logger.add(
                sys.stderr,
                level=log_level,
                format=(
                    _compact_log_format
                    if console_colorize
                    else _plain_compact_log_format
                ),
                colorize=console_colorize,
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
        except Exception as error:
            logger.remove()
            raise RuntimeError("Failed to configure logging sinks") from error


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
