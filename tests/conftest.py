"""Shared test fixtures."""

from collections.abc import Iterator
from pathlib import Path
from threading import Lock

import pytest
from loguru import logger

_LOGGER_LOCK = Lock()


@pytest.fixture
def log_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return the isolated log path configured for the current test."""
    path = tmp_path / "test.log"
    # monkeypatch restores the previous environment value after the test.
    monkeypatch.setenv("LOG_FILE", str(path))
    return path


@pytest.fixture(autouse=True)
def _isolate_logger(log_file: Path) -> Iterator[None]:
    """Serialize handler reconfiguration and clean up Loguru after each test."""
    # Each xdist worker has its own logger and lock. Complete the queued file
    # sink before removing handlers so records cannot leak across test teardown.
    with _LOGGER_LOCK:
        yield
        logger.complete()
        logger.remove()
