"""pytest fixtures — in-memory SQLite for fast tests; Postgres via env for integration."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Minimum env so `Settings()` validates; individual tests override if needed.
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("ADMIN_API_KEY", "gdr_admin_test_1234567890")
    monkeypatch.setenv(
        "DATABASE_URL",
        os.environ.get("GODERASH_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"),
    )
    monkeypatch.setenv("GODERASH_ENV", "dev")
