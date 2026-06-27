"""Tests for obs/alerts.py — email composition + per-run-per-day dedup (DB + Resend mocked)."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest

from policy_crawler.obs import alerts


@pytest.fixture(autouse=True)
def _email_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    from policy_crawler.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("DIGEST_FROM_EMAIL", "from@example.com")
    monkeypatch.setenv("DIGEST_TO_EMAIL", "to@example.com")
    monkeypatch.setenv("WEBAPP_BASE_URL", "https://app.example.com")
    yield
    get_settings.cache_clear()


class _StatefulCur:
    """Mimics the SELECT alert_sent_at / UPDATE jsonb_set cycle against one slot."""

    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store
        self._last_select: str | None = None

    def __enter__(self) -> _StatefulCur:
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        if sql.strip().upper().startswith("SELECT"):
            self._last_select = "sent"
        elif sql.strip().upper().startswith("UPDATE"):
            self._store["sent"] = params[0]  # the ISO timestamp

    def fetchone(self) -> dict[str, Any]:
        return {"sent": self._store.get("sent")}


class _Conn:
    def __init__(self, cur: _StatefulCur) -> None:
        self._cur = cur

    def cursor(self) -> _StatefulCur:
        return self._cur


@pytest.fixture
def sent_emails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    store: dict[str, Any] = {}

    @contextmanager
    def fake_connection() -> Generator[_Conn, None, None]:
        yield _Conn(_StatefulCur(store))

    monkeypatch.setattr(alerts, "connection", fake_connection)

    import resend

    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(resend.Emails, "send", lambda payload: captured.append(payload))
    return captured


def test_failure_email_sends_with_expected_subject_and_body(
    sent_emails: list[dict[str, Any]],
) -> None:
    run_id = uuid4()
    sent = alerts.send_failure_email(run_id, "weekly", "boom: something broke")

    assert sent is True
    assert len(sent_emails) == 1
    msg = sent_emails[0]
    assert msg["to"] == ["to@example.com"]
    assert msg["subject"].startswith("[policy-crawler] weekly run failed ")
    assert "boom: something broke" in msg["text"]
    assert "https://app.example.com/status" in msg["text"]
    assert str(run_id) in msg["text"]


def test_failure_email_deduped_within_day(sent_emails: list[dict[str, Any]]) -> None:
    run_id = uuid4()
    first = alerts.send_failure_email(run_id, "weekly", "boom")
    second = alerts.send_failure_email(run_id, "weekly", "boom again")

    assert first is True
    assert second is False  # deduped — alert_sent_at already set today
    assert len(sent_emails) == 1


def test_warning_email_truncates_to_50_lines(sent_emails: list[dict[str, Any]]) -> None:
    long_error = "\n".join(f"line {i}" for i in range(200))
    alerts.send_failure_email(uuid4(), "daily", long_error)

    body = sent_emails[0]["text"]
    # The error tail keeps at most 50 lines; line 0..149 must be dropped.
    assert "line 199" in body
    assert "line 149" not in body


def test_no_email_config_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    from policy_crawler.config import get_settings

    get_settings.cache_clear()
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    @contextmanager
    def fake_connection() -> Generator[_Conn, None, None]:
        yield _Conn(_StatefulCur({}))

    monkeypatch.setattr(alerts, "connection", fake_connection)
    assert alerts.send_failure_email(uuid4(), "daily", "boom") is False
    get_settings.cache_clear()
