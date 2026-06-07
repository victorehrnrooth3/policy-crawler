"""Tests for execute_write's retry-on-dropped-connection behavior (no live DB)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import psycopg
import pytest


def test_execute_write_succeeds_first_try() -> None:
    from policy_crawler import db

    conn = MagicMock()

    @contextmanager
    def fake_connection():
        yield conn

    calls: list[str] = []
    with patch.object(db, "connection", fake_connection):
        db.execute_write(lambda c: calls.append("work"))

    assert calls == ["work"]


def test_execute_write_retries_on_dropped_connection() -> None:
    from policy_crawler import db

    conn = MagicMock()

    @contextmanager
    def fake_connection():
        yield conn

    attempts = {"n": 0}

    def work(_c: object) -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise psycopg.OperationalError("SSL connection has been closed unexpectedly")
        # second attempt succeeds

    with (
        patch.object(db, "connection", fake_connection),
        patch.object(db, "reset_pool") as mock_reset,
    ):
        db.execute_write(work)

    assert attempts["n"] == 2
    mock_reset.assert_called_once()


def test_execute_write_raises_after_exhausting_retries() -> None:
    from policy_crawler import db

    conn = MagicMock()

    @contextmanager
    def fake_connection():
        yield conn

    def work(_c: object) -> None:
        raise psycopg.OperationalError("still dead")

    with (
        patch.object(db, "connection", fake_connection),
        patch.object(db, "reset_pool") as mock_reset,
        pytest.raises(psycopg.OperationalError, match="still dead"),
    ):
        db.execute_write(work, retries=2)

    # reset attempted on each of the 3 failed attempts (initial + 2 retries)
    assert mock_reset.call_count == 3
