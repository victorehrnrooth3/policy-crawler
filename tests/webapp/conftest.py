"""Shared fixtures for webapp tests."""

from __future__ import annotations

import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

_MOCK_HMAC = "test-hmac-secret-at-least-32bytes!!"
_MOCK_SESSION = "test-session-secret-32bytes-!!!!"
_MOCK_BASE_URL = "https://app.example.com"
_MOCK_EMAIL = "test@example.com"


@pytest.fixture(autouse=True)
def _webapp_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    from policy_crawler.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("TOKEN_HMAC_SECRET", _MOCK_HMAC)
    monkeypatch.setenv("SESSION_COOKIE_SECRET", _MOCK_SESSION)
    monkeypatch.setenv("WEBAPP_BASE_URL", _MOCK_BASE_URL)
    monkeypatch.setenv("DIGEST_TO_EMAIL", _MOCK_EMAIL)
    monkeypatch.setenv("DIGEST_FROM_EMAIL", "from@example.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    from policy_crawler.webapp.main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def auth_cookies() -> dict[str, str]:
    """Return a valid signed session cookie for the mock user."""
    from policy_crawler.webapp.auth import _sign_payload

    now = int(time.time())
    cookie = _sign_payload({"email": _MOCK_EMAIL, "iat": now, "exp": now + 86400})
    return {"session": cookie}


@pytest.fixture
def csrf_cookies() -> dict[str, str]:
    return {"csrf_token": "test-csrf-token-abc123"}


def _make_mock_conn(rows: list[Any] | None = None, rowcount: int = 1) -> MagicMock:
    """Build a nested MagicMock that mimics `with connection() as conn, conn.cursor() as cur`."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.rowcount = rowcount
    if rows is not None:
        cur.fetchone.return_value = rows[0] if rows else None
        cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    return conn
