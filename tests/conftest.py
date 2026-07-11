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
    """Serialize access to Loguru and clean up its global handlers per test."""
    # enqueue=False keeps all sink work inside this locked test window. xdist
    # workers run in separate processes, each with its own logger and lock.
    with _LOGGER_LOCK:
        yield
        logger.remove()
