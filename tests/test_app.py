import os
import re
from pathlib import PureWindowsPath
from unittest.mock import patch

import pytest
from loguru import logger

from second_brain.app import (
    _compact_log_format,
    configure_logging,
    main,
)

EXPECTED_LABELS = {
    "debug message": "DEBUG",
    "info message": "INFO",
    "warning message": "WARN",
    "error message": "ERR",
}
CUSTOM_LEVELS = {"SUCCESS": 25, "TRACE": 5}


def _ensure_custom_levels_registered():
    """Register custom levels when the installed Loguru lacks them."""
    for level_name, level_number in CUSTOM_LEVELS.items():
        try:
            logger.level(level_name)
        except ValueError:
            logger.level(level_name, no=level_number)


def _assert_compact_lines(output):
    lines = output.splitlines()
    expected_lines = list(EXPECTED_LABELS.items())
    assert len(lines) == len(expected_lines)

    for index, line in enumerate(lines):
        message, label = expected_lines[index]
        assert re.fullmatch(
            rf"\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}"
            rf" \| {label} \| (?:tests\.)?test_app:test_compact_log_format:\d+"
            rf" \| {message}",
            line,
        )


def test_compact_log_format(capfd, log_file):
    configure_logging()

    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")

    console_output = capfd.readouterr().err
    file_output = log_file.read_text()

    _assert_compact_lines(console_output)
    _assert_compact_lines(file_output)


def test_log_file_fixture_wires_configure_logging(log_file):
    """Verify that configuration writes to the fixture's temporary path."""
    configure_logging()

    logger.info("fixture path message")

    assert log_file.is_file()
    assert "fixture path message" in log_file.read_text()


def test_logger_state_is_isolated_per_worker(worker_id, log_file):
    """Verify that each xdist process writes through its own logger state."""
    configure_logging()
    marker = f"worker={worker_id} pid={os.getpid()}"

    logger.info(marker)

    assert os.environ.get("PYTEST_XDIST_WORKER", "master") == worker_id
    assert marker in log_file.read_text()


def test_configured_thresholds_are_preserved(capfd, log_file, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging()

    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")

    console_output = capfd.readouterr().err
    file_output = log_file.read_text()

    assert "debug message" not in console_output
    assert "info message" not in console_output
    assert "WARN" in console_output
    assert "ERR" in console_output
    assert all(message in file_output for message in EXPECTED_LABELS)


def test_invalid_log_level_is_rejected(monkeypatch):
    """Document Loguru's failure behavior for an invalid console level."""
    monkeypatch.setenv("LOG_LEVEL", "INVALID_LEVEL")

    with pytest.raises(ValueError, match="Level 'INVALID_LEVEL' does not exist"):
        configure_logging()


@pytest.mark.parametrize(
    ("level_name", "expected_label"),
    [("SUCCESS", "SUCCESS"), ("TRACE", "TRACE")],
)
def test_custom_loguru_levels_retained(level_name, expected_label, capfd, monkeypatch):
    """Verify that non-mapped Loguru levels retain their original names."""
    _ensure_custom_levels_registered()
    monkeypatch.setenv("LOG_LEVEL", "TRACE")
    configure_logging()

    logger.log(level_name, "custom level message")

    console_output = capfd.readouterr().err
    expected_output = f" | {expected_label} | "

    assert expected_output in console_output


def test_success_level_is_registered(log_file):
    """Verify that SUCCESS is available with its expected severity."""
    _ensure_custom_levels_registered()

    assert logger.level("SUCCESS").no == CUSTOM_LEVELS["SUCCESS"]
    assert log_file.parent.exists()


def test_file_retention_is_preserved():
    """Verify that compact formatting does not change file retention."""
    with (
        patch("second_brain.app.logger.remove"),
        patch("second_brain.app.logger.add") as add_sink,
    ):
        configure_logging()

    assert add_sink.call_args_list[1].kwargs["retention"] == 1


def test_windows_log_path_is_passed_to_file_sink(monkeypatch):
    """Verify that Windows paths reach Loguru without reinterpretation."""
    windows_log_file = PureWindowsPath(
        "C:/Users/you/AppData/Local/second-brain/app.log"
    )
    monkeypatch.setenv("LOG_FILE", str(windows_log_file))

    with (
        patch("second_brain.app.logger.remove"),
        patch("second_brain.app.logger.add") as add_sink,
    ):
        configure_logging()

    assert add_sink.call_args_list[1].args[0] == str(windows_log_file)


def test_compact_formatter_preserves_extra_metadata():
    """Verify that formatting does not mutate caller-provided metadata."""
    record = {
        "level": logger.level("INFO"),
        "extra": {"request_id": "example-request"},
    }

    _compact_log_format(record)

    assert record["extra"] == {"request_id": "example-request"}


def test_compact_log_format_preserves_exceptions(capfd, log_file):
    """Verify that exception details follow the compact log line."""
    configure_logging()

    try:
        raise ValueError("example failure")
    except ValueError:
        logger.exception("operation failed")

    console_output = capfd.readouterr().err

    assert re.search(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
        r" \| ERR \| (?:[\w.]+\.)?test_app:"
        r"test_compact_log_format_preserves_exceptions:\d+"
        r" \| operation failed\n",
        console_output,
    )
    assert "operation failed\nTraceback (most recent call last):" in console_output
    assert (
        "test_compact_log_format_preserves_exceptions\n"
        '    raise ValueError("example failure")' in console_output
    )
    assert "ValueError: example failure" in console_output
    file_output = log_file.read_text()
    assert "{exception}" not in console_output
    assert "{exception}" not in file_output
    assert "ValueError: example failure" in file_output


def test_main_logs_greeting(capfd, log_file):
    main()
    captured = capfd.readouterr()
    assert "Hello from second_brain!" in captured.err
    assert "Hello from second_brain!" in log_file.read_text()
