"""Shared test fixtures."""

import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def log_file(tmp_path, monkeypatch):
    """Configure an isolated log file and clean up Loguru after each test."""
    path = tmp_path / "test.log"
    monkeypatch.setenv("LOG_FILE", str(path))
    yield path
    logger.remove()
