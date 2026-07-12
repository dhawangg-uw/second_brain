import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import PureWindowsPath
from unittest.mock import patch

import pytest
from loguru import logger

from second_brain.app import (
    _compact_log_format,
    _plain_compact_log_format,
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


def _read_log_file(log_file):
    """Wait for queued file records, then return their text."""
    logger.complete()
    return log_file.read_text()


def _sink_call(add_sink, target):
    """Return the logger.add() call for a sink without relying on call order."""
    return next(call for call in add_sink.call_args_list if call.args[0] == target)


def _assert_compact_standard_lines(output):
    """Assert the four single-line records; exceptions use dedicated assertions."""
    lines = output.splitlines()
    expected_lines = list(EXPECTED_LABELS.items())
    assert len(lines) == len(expected_lines)

    for index, line in enumerate(lines):
        message, label = expected_lines[index]
        assert re.fullmatch(
            rf"\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}"
            rf" \| {label} \| [^|\n]+:[^:|\n]+:\d+"
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
    file_output = _read_log_file(log_file)

    _assert_compact_standard_lines(console_output)
    _assert_compact_standard_lines(file_output)


def test_log_file_fixture_wires_configure_logging(log_file):
    """Verify that configuration writes to the fixture's temporary path."""
    configure_logging()

    logger.info("fixture path message")

    assert log_file.is_file()
    assert "fixture path message" in _read_log_file(log_file)


def test_logger_state_is_isolated_per_worker(worker_id, log_file):
    """Verify that each xdist process writes through its own logger state."""
    configure_logging()
    marker = f"worker={worker_id} pid={os.getpid()}"

    logger.info(marker)

    assert os.environ.get("PYTEST_XDIST_WORKER", "master") == worker_id
    assert marker in _read_log_file(log_file)


def test_synchronous_file_sink_accepts_concurrent_writes(log_file):
    """Verify Loguru serializes writes made concurrently by application threads."""
    configure_logging()
    messages = [f"thread message {index}" for index in range(20)]

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(logger.info, messages))

    logged_messages = [
        line.rsplit(" | ", 1)[-1] for line in _read_log_file(log_file).splitlines()
    ]
    assert sorted(logged_messages) == sorted(messages)


def test_configured_thresholds_are_preserved(capfd, log_file, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging()

    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")

    console_output = capfd.readouterr().err
    file_output = _read_log_file(log_file)

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

    assert _sink_call(add_sink, os.environ["LOG_FILE"]).kwargs["retention"] == 1


def test_configured_sink_color_modes():
    """Keep ANSI markup out of files while allowing terminal color detection."""
    with (
        patch("second_brain.app.logger.remove"),
        patch("second_brain.app.logger.add") as add_sink,
    ):
        configure_logging()

    stderr_call = _sink_call(add_sink, sys.stderr)
    file_call = _sink_call(add_sink, os.environ["LOG_FILE"])
    assert stderr_call.kwargs["colorize"] is False
    assert stderr_call.kwargs["format"] is _plain_compact_log_format
    assert stderr_call.kwargs["enqueue"] is False
    assert file_call.kwargs["colorize"] is False
    assert file_call.kwargs["format"] is _plain_compact_log_format
    assert file_call.kwargs["enqueue"] is True


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

    assert _sink_call(add_sink, str(windows_log_file)).args[0] == str(windows_log_file)


def test_compact_formatter_preserves_extra_metadata():
    """Verify that formatting does not mutate caller-provided metadata."""
    record = {
        "level": logger.level("INFO"),
        "extra": {"request_id": "example-request"},
    }

    _compact_log_format(record)

    assert record["extra"] == {"request_id": "example-request"}


@pytest.mark.parametrize("record", [{}, {"level": object()}])
def test_compact_formatter_handles_malformed_level(record):
    """Keep formatter construction safe for incomplete external records."""
    assert "<level>UNKNOWN</level>" in _compact_log_format(record)


def test_compact_formatter_escapes_level_format_braces():
    """Prevent custom level names from introducing format placeholders."""
    level = type("CustomLevel", (), {"name": "CUSTOM{value}"})()

    assert "CUSTOM{{value}} |" in _plain_compact_log_format({"level": level})


def test_compact_formatter_accepts_real_loguru_record():
    """Verify compatibility with records produced by the installed Loguru."""
    records = []
    sink_id = logger.add(lambda message: records.append(message.record))
    try:
        logger.info("real record")
    finally:
        logger.remove(sink_id)

    assert "INFO |" in _plain_compact_log_format(records[0])


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
        r" \| ERR \| [^|\n]+:[^:|\n]+:\d+"
        r" \| operation failed\n",
        console_output,
    )
    assert "operation failed\nTraceback (most recent call last):" in console_output
    assert (
        "test_compact_log_format_preserves_exceptions\n"
        '    raise ValueError("example failure")' in console_output
    )
    assert "ValueError: example failure" in console_output
    file_output = _read_log_file(log_file)
    assert "{exception}" not in console_output
    assert "{exception}" not in file_output
    assert "ValueError: example failure" in file_output


def test_main_logs_greeting(capfd, log_file):
    main()
    captured = capfd.readouterr()
    assert "Hello from second_brain!" in captured.err
    assert "Hello from second_brain!" in _read_log_file(log_file)
