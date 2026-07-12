import importlib.metadata
import os
import pickle
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import PureWindowsPath
from unittest.mock import patch

import pytest
from loguru import logger

from second_brain.app import (
    _compact_log_format,
    _env_flag,
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


def test_minimum_loguru_api_contract():
    """Keep the pinned Loguru floor aligned with APIs used at runtime."""
    version = tuple(
        int(part) for part in importlib.metadata.version("loguru").split(".")[:3]
    )
    assert version >= (0, 7, 3)
    assert callable(logger.complete)
    assert callable(logger.catch)


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


def test_callable_formats_expand_record_placeholders(capfd, log_file):
    """Verify Loguru expands templates returned by format callables."""
    configure_logging()

    logger.info("callable format integration")

    for output in (capfd.readouterr().err, _read_log_file(log_file)):
        assert "{name}" not in output
        assert "{function}" not in output
        assert " | second_brain.app:" not in output
        assert "test_app:test_callable_formats_expand_record_placeholders:" in output


def test_log_file_fixture_wires_configure_logging(log_file):
    """Verify that configuration writes to the fixture's temporary path."""
    configure_logging()

    logger.info("fixture path message")

    assert log_file.is_file()
    assert "fixture path message" in _read_log_file(log_file)


def test_logger_state_is_isolated_per_worker(request, log_file):
    """Verify that each xdist process writes through its own logger state."""
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    configure_logging()
    marker = f"worker={worker_id} pid={os.getpid()}"

    logger.info(marker)

    assert os.environ.get("PYTEST_XDIST_WORKER", "master") == worker_id
    assert marker in _read_log_file(log_file)


def test_queued_file_sink_accepts_concurrent_writes(log_file):
    """Verify Loguru serializes writes made concurrently by application threads."""
    configure_logging()
    messages = [f"thread message {index}" for index in range(20)]

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(logger.info, messages))

    logged_messages = [
        line.rsplit(" | ", 1)[-1] for line in _read_log_file(log_file).splitlines()
    ]
    assert sorted(logged_messages) == sorted(messages)


def test_concurrent_configuration_replaces_handlers_atomically(log_file):
    """Serialize remove/add transactions when startup callers overlap."""
    events = []

    with patch(
        "second_brain.app.logger.remove", side_effect=lambda: events.append("R")
    ):
        with patch(
            "second_brain.app.logger.add",
            side_effect=lambda *_args, **_kwargs: events.append("A"),
        ):
            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(lambda _index: configure_logging(), range(8)))

    assert events == ["R", "A", "A"] * 8
    assert log_file.parent.exists()


def test_reconfiguration_resnapshots_color_environment(monkeypatch):
    """Apply LOG_COLORIZE changes made between complete configuration calls."""
    with patch("second_brain.app.logger.remove"):
        with patch("second_brain.app.logger.add") as add_sink:
            configure_logging()
            first_console = _sink_call(add_sink, sys.stderr)
            monkeypatch.setenv("LOG_COLORIZE", "true")
            add_sink.reset_mock()
            configure_logging()
            second_console = _sink_call(add_sink, sys.stderr)

    assert first_console.kwargs.get("colorize") is False
    assert second_console.kwargs.get("colorize") is True


def test_queued_formatter_works_in_spawned_process(log_file):
    """Verify the module-level formatter works in a separate Python process."""
    env = os.environ | {"LOG_FILE": str(log_file)}
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from loguru import logger; "
            "from second_brain.app import configure_logging; "
            "configure_logging(); logger.info('spawned process message'); "
            "logger.complete()",
        ],
        check=True,
        env=env,
    )

    assert "spawned process message" in log_file.read_text()


@pytest.mark.parametrize("formatter", [_compact_log_format, _plain_compact_log_format])
def test_formatters_are_picklable_for_spawn_workers(formatter):
    """Keep queued formatters importable by spawn-based multiprocessing."""
    assert pickle.loads(pickle.dumps(formatter)) is formatter


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

    with pytest.raises(ValueError, match="^Invalid LOG_LEVEL: 'INVALID_LEVEL'$"):
        configure_logging()


def test_invalid_level_does_not_partially_reconfigure_handlers(monkeypatch):
    """Validate first so a rejected setting leaves installed handlers intact."""
    monkeypatch.setenv("LOG_LEVEL", "INVALID_LEVEL")

    with patch("second_brain.app.logger.remove") as remove:
        with patch("second_brain.app.logger.add") as add:
            with pytest.raises(ValueError):
                configure_logging()

    remove.assert_not_called()
    add.assert_not_called()


def test_main_drains_logger_when_configuration_fails(monkeypatch):
    """Keep cleanup safe when startup rejects configuration before adding sinks."""
    monkeypatch.setenv("LOG_LEVEL", "INVALID_LEVEL")

    with patch("second_brain.app.logger.complete") as complete:
        with pytest.raises(ValueError, match="^Invalid LOG_LEVEL"):
            main()

    assert complete.call_count >= 1


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


def test_file_retention_is_preserved(log_file):
    """Verify that compact formatting does not change file retention."""
    with patch("second_brain.app.logger.remove"):
        with patch("second_brain.app.logger.add") as add_sink:
            configure_logging()

    assert _sink_call(add_sink, str(log_file)).kwargs.get("retention") == 1


def test_file_rotation_preserves_compact_output(log_file):
    """Exercise rotation and the single-backup retention policy together."""
    configure_logging()

    for index in range(3):
        logger.info(f"rotation marker {index} " + "x" * 60_000)
        logger.complete()

    rotated_files = list(log_file.parent.glob(f"{log_file.stem}.*{log_file.suffix}"))
    assert len(rotated_files) == 1
    assert " | INFO | " in rotated_files[0].read_text()
    assert log_file.is_file()


def test_configured_sink_color_modes(log_file):
    """Keep ANSI markup out of files while allowing terminal color detection."""
    with patch("second_brain.app.logger.remove"):
        with patch("second_brain.app.logger.add") as add_sink:
            configure_logging()

    stderr_call = _sink_call(add_sink, sys.stderr)
    file_call = _sink_call(add_sink, str(log_file))
    assert stderr_call.kwargs.get("colorize") is False
    assert stderr_call.kwargs.get("enqueue") is False
    assert file_call.kwargs.get("colorize") is False
    assert file_call.kwargs.get("enqueue") is True


def test_console_colors_can_be_enabled(monkeypatch):
    """Provide an opt-in escape hatch for interactive terminal colors."""
    monkeypatch.setenv("LOG_COLORIZE", "true")
    with patch("second_brain.app.logger.remove"):
        with patch("second_brain.app.logger.add") as add_sink:
            configure_logging()

    stderr_call = _sink_call(add_sink, sys.stderr)
    assert stderr_call.kwargs.get("colorize") is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("t", True),
        (" yes ", True),
        ("y", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("off", False),
        ("", False),
    ],
)
def test_environment_flag_parsing(value, expected, monkeypatch):
    """Keep documented truthy values and falsey fallbacks synchronized."""
    monkeypatch.setenv("EXAMPLE_FLAG", value)
    assert _env_flag("EXAMPLE_FLAG") is expected


def test_file_sink_stays_plain_when_console_colors_enabled(log_file, monkeypatch):
    """Never allow terminal markup or ANSI escapes into the file sink."""
    monkeypatch.setenv("LOG_COLORIZE", "true")
    configure_logging()

    logger.info("colored console plain file")

    file_output = _read_log_file(log_file)
    assert "<level>" not in file_output
    assert "\x1b[" not in file_output


def test_real_sinks_separate_terminal_markup_from_file_output(
    capfd, log_file, monkeypatch
):
    """Exercise color rendering and stripping through real Loguru sinks."""
    monkeypatch.setenv("LOG_COLORIZE", "true")
    configure_logging()

    logger.warning("sink color integration")

    console_output = capfd.readouterr().err
    file_output = _read_log_file(log_file)
    assert "\x1b[" in console_output
    assert "\x1b[" not in file_output
    assert "<level>" not in file_output
    assert "sink color integration" in file_output


def test_windows_log_path_is_passed_to_file_sink(monkeypatch):
    """Verify that Windows paths reach Loguru without reinterpretation."""
    windows_log_file = PureWindowsPath(
        "C:/Users/you/AppData/Local/second-brain/app.log"
    )
    monkeypatch.setenv("LOG_FILE", str(windows_log_file))

    with patch("second_brain.app.logger.remove"):
        with patch("second_brain.app.logger.add") as add_sink:
            configure_logging()

    file_call = next(
        call for call in add_sink.call_args_list if "rotation" in call.kwargs
    )
    actual = str(file_call.args[0]).replace("\\", "/").casefold()
    expected = str(windows_log_file).replace("\\", "/").casefold()
    assert actual == expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows integration coverage")
def test_windows_log_path_creates_file(tmp_path, monkeypatch):
    """Verify Loguru creates and writes the configured file on Windows."""
    log_file = tmp_path / "windows-test.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    configure_logging()

    logger.info("windows file message")

    assert "windows file message" in _read_log_file(log_file)


def test_compact_formatter_preserves_extra_metadata():
    """Verify that formatting does not mutate caller-provided metadata."""
    record = {
        "level": logger.level("INFO"),
        "extra": {"request_id": "example-request"},
    }

    _compact_log_format(record)

    assert record["extra"] == {"request_id": "example-request"}


@pytest.mark.parametrize(("record", "label"), [({}, "UNKNOWN"), ({"level": 20}, "20")])
def test_compact_formatter_handles_nonstandard_level_shape(record, label):
    """Provide stable labels for missing or scalar external level values."""
    assert f"<level>{label}</level>" in _compact_log_format(record)


def test_compact_formatter_escapes_level_format_braces():
    """Prevent custom level names from introducing format placeholders."""
    level = type("CustomLevel", (), {"name": "CUSTOM{value}"})()

    assert "CUSTOM{{value}} |" in _plain_compact_log_format({"level": level})


def test_exotic_custom_level_renders_literally(capfd, log_file, monkeypatch):
    """Render braces, colons, and percent signs safely in a real custom level."""
    level_name = "EXOTIC:{value}%"
    try:
        logger.level(level_name)
    except ValueError:
        logger.level(level_name, no=35)
    monkeypatch.setenv("LOG_LEVEL", "TRACE")
    configure_logging()

    logger.log(level_name, "exotic level message")

    expected = f" | {level_name} | "
    assert expected in capfd.readouterr().err
    assert expected in _read_log_file(log_file)


def test_compact_format_preserves_message_braces(capfd, log_file):
    """Treat braces in user-supplied record data as literal message text."""
    configure_logging()

    logger.info("user payload: {name} {function} {message}")

    expected = "user payload: {name} {function} {message}"
    assert expected in capfd.readouterr().err
    assert expected in _read_log_file(log_file)


def test_compact_format_preserves_braces_from_format_arguments(capfd, log_file):
    """Keep braces literal after Loguru interpolates user format arguments."""
    configure_logging()

    logger.info("user payload: {}", "{nested.value}")

    expected = "user payload: {nested.value}"
    assert expected in capfd.readouterr().err
    assert expected in _read_log_file(log_file)


def test_compact_format_preserves_long_function_name(log_file):
    """Keep long source fields intact on a single compact log line."""

    def function_with_an_intentionally_long_name_for_source_location_coverage():
        logger.info("long source message")

    configure_logging()
    function_with_an_intentionally_long_name_for_source_location_coverage()

    output = _read_log_file(log_file)
    assert (
        "function_with_an_intentionally_long_name_for_source_location_coverage"
        in output
    )
    assert len(output.splitlines()) == 1


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


def test_main_logs_and_reraises_unexpected_errors():
    """Keep CLI failures visible to callers after Loguru records them."""
    with patch("second_brain.app.configure_logging", side_effect=RuntimeError("boom")):
        with patch("second_brain.app.logger.complete") as complete:
            with pytest.raises(RuntimeError, match="boom"):
                main()

    assert complete.call_count >= 1


def test_main_flushes_queued_logs_on_normal_shutdown():
    """Drain asynchronous sinks before the CLI returns."""
    with patch("second_brain.app.configure_logging"):
        with patch("second_brain.app.logger.info"):
            with patch("second_brain.app.logger.complete") as complete:
                main()

    assert complete.call_count >= 1
