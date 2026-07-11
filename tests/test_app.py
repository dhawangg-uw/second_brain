import re

from loguru import logger

from second_brain.app import configure_logging, main

EXPECTED_LABELS = {
    "debug message": "DEBUG",
    "info message": "INFO",
    "warning message": "WARN",
    "error message": "ERR",
}


def _assert_compact_lines(output):
    lines = output.splitlines()
    assert len(lines) == len(EXPECTED_LABELS)

    for line, (message, label) in zip(lines, EXPECTED_LABELS.items(), strict=True):
        assert re.fullmatch(
            rf"\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}"
            rf" \| {label} \| tests\.test_app:test_compact_log_format:\d+"
            rf" \| {message}",
            line,
        )


def test_compact_log_format(capfd, tmp_path, monkeypatch):
    log_file = tmp_path / "test.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    configure_logging()

    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")

    console_output = capfd.readouterr().err
    file_output = log_file.read_text()

    _assert_compact_lines(console_output)
    _assert_compact_lines(file_output)


def test_configured_thresholds_are_preserved(capfd, tmp_path, monkeypatch):
    log_file = tmp_path / "test.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
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


def test_main_logs_greeting(capfd):
    main()
    captured = capfd.readouterr()
    assert "Hello from second_brain!" in captured.err
