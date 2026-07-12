"""Shared test fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from loguru import logger


@pytest.fixture
def log_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return the isolated log path configured for the current test."""
    path = tmp_path / "test.log"
    # monkeypatch restores the previous environment value after the test.
    monkeypatch.setenv("LOG_FILE", str(path))
    return path


@pytest.fixture(autouse=True)
def _isolate_logger(log_file: Path) -> Iterator[None]:
    """Configure every test's path, then clean up its process-local logger.

    Depending on ``log_file`` is intentional: pytest resolves that fixture and
    sets ``LOG_FILE`` even when the test function does not request it directly.
    """
    yield
    logger.complete()
    logger.remove()
