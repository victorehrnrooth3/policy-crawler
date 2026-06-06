"""Tests for vote-link and magic-link routes."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.webapp.conftest import _make_mock_conn

# ── Helpers ──────────────────────────────────────────────────────────────────


def _vote_token(job_id: str | None = None) -> str:
    from policy_crawler.digest.tokens import make_token

    return make_token({"job_id": job_id or str(uuid4()), "vote": "up"}, "vote", timedelta(days=14))


def _magic_token(job_id: str | None = None) -> str:
    from policy_crawler.digest.tokens import MAGIC_LINK_TOKEN_TTL, make_token

    payload = {"purpose": "session"}
    if job_id:
        payload["job_id"] = job_id
    return make_token(payload, "magic_link", MAGIC_LINK_TOKEN_TTL)


# ── GET /v/{action}/{token} ───────────────────────────────────────────────────


def test_vote_up_records_feedback(client: TestClient) -> None:
    job_id = str(uuid4())
    token = _vote_token(job_id)

    conn = _make_mock_conn(rows=[{"title": "Climate Analyst"}], rowcount=1)

    with patch("policy_crawler.webapp.routes.votes.connection", return_value=conn):
        resp = client.get(f"/v/up/{token}", follow_redirects=False)

    assert resp.status_code == 200
    body = resp.text
    assert "confirmed" in body.lower() or "vote" in body.lower()


def test_vote_already_used_shows_already_recorded(client: TestClient) -> None:
    job_id = str(uuid4())
    token = _vote_token(job_id)

    # rowcount=0 means ON CONFLICT DO NOTHING affected 0 rows
    conn = _make_mock_conn(rows=[], rowcount=0)

    with patch("policy_crawler.webapp.routes.votes.connection", return_value=conn):
        resp = client.get(f"/v/up/{token}")

    assert resp.status_code == 200
    assert "already" in resp.text.lower()


def test_vote_invalid_action_returns_400(client: TestClient) -> None:
    token = _vote_token()
    resp = client.get(f"/v/invalid/{token}")
    assert resp.status_code == 400


def test_vote_invalid_token_returns_400(client: TestClient) -> None:
    resp = client.get("/v/up/not-a-real-token")
    assert resp.status_code == 400


def test_vote_expired_token_returns_400(client: TestClient) -> None:
    from policy_crawler.digest.tokens import make_token

    token = make_token({"job_id": str(uuid4())}, "vote", timedelta(seconds=-1))
    resp = client.get(f"/v/up/{token}")
    assert resp.status_code == 400


# ── POST /v/feedback/{token} ─────────────────────────────────────────────────


def test_feedback_post_within_window(client: TestClient, csrf_cookies: dict[str, str]) -> None:
    job_id = str(uuid4())
    token = _vote_token(job_id)

    conn = _make_mock_conn(rows=[{"nonce": "x"}])

    with patch("policy_crawler.webapp.routes.votes.connection", return_value=conn):
        resp = client.post(
            f"/v/feedback/{token}",
            data={"freetext": "Great role!", "csrf_token": "test-csrf-token-abc123"},
            cookies=csrf_cookies,
        )

    assert resp.status_code == 200
    assert "feedback" in resp.text.lower() or "saved" in resp.text.lower()


def test_feedback_csrf_required(client: TestClient) -> None:
    token = _vote_token()
    # No CSRF cookie — verify_csrf fails
    resp = client.post(f"/v/feedback/{token}", data={"freetext": "hi", "csrf_token": "wrong"})
    assert resp.status_code == 403


def test_feedback_expired_window_shows_expired(
    client: TestClient, csrf_cookies: dict[str, str]
) -> None:
    job_id = str(uuid4())
    token = _vote_token(job_id)

    # fetchone returns None → window check fails
    conn = _make_mock_conn(rows=[None])
    conn.__enter__.return_value.cursor.return_value.fetchone.return_value = None

    with patch("policy_crawler.webapp.routes.votes.connection", return_value=conn):
        resp = client.post(
            f"/v/feedback/{token}",
            data={"freetext": "Too late", "csrf_token": "test-csrf-token-abc123"},
            cookies=csrf_cookies,
        )

    assert resp.status_code == 200
    assert "expired" in resp.text.lower() or "window" in resp.text.lower()


# ── GET /m/{token} ────────────────────────────────────────────────────────────


def test_magic_link_sets_session_and_redirects(client: TestClient) -> None:
    token = _magic_token()
    resp = client.get(f"/m/{token}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/inbox"
    assert "session" in resp.cookies


def test_magic_link_with_job_id_redirects_to_detail(client: TestClient) -> None:
    job_id = str(uuid4())
    token = _magic_token(job_id=job_id)
    resp = client.get(f"/m/{token}", follow_redirects=False)
    assert resp.status_code == 303
    assert f"/inbox/{job_id}" in resp.headers["location"]


def test_magic_link_invalid_token_returns_400(client: TestClient) -> None:
    resp = client.get("/m/not-a-valid-token")
    assert resp.status_code == 400


# ── POST /auth/magic-link ─────────────────────────────────────────────────────


def test_request_magic_link_sends_email(client: TestClient, csrf_cookies: dict[str, str]) -> None:
    with patch("policy_crawler.webapp.routes.votes.resend") as mock_resend:
        mock_resend.Emails.send.return_value = MagicMock(id="email-id-123")
        resp = client.post(
            "/auth/magic-link",
            data={"csrf_token": "test-csrf-token-abc123"},
            cookies=csrf_cookies,
        )

    assert resp.status_code == 200
    assert "email" in resp.text.lower() or "link" in resp.text.lower()


def test_request_magic_link_csrf_required(client: TestClient) -> None:
    resp = client.post("/auth/magic-link", data={"csrf_token": "bad"})
    assert resp.status_code == 403


# ── Webapp vote buttons (POST /v/webapp/{job_id}/{action}) ───────────────────


def test_webapp_vote_requires_session(client: TestClient) -> None:
    job_id = str(uuid4())
    resp = client.post(
        f"/v/webapp/{job_id}/up",
        data={"csrf_token": "test-csrf-token-abc123"},
        cookies={"csrf_token": "test-csrf-token-abc123"},
        follow_redirects=False,
    )
    # Should redirect to auth (401 or 303 to login)
    assert resp.status_code in (401, 303)


def test_webapp_vote_records_feedback(
    client: TestClient, auth_cookies: dict[str, str], csrf_cookies: dict[str, str]
) -> None:
    job_id = str(uuid4())
    conn = _make_mock_conn(rows=[])

    with patch("policy_crawler.webapp.routes.votes.connection", return_value=conn):
        resp = client.post(
            f"/v/webapp/{job_id}/up",
            data={"csrf_token": "test-csrf-token-abc123"},
            cookies={**auth_cookies, **csrf_cookies},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert f"/inbox/{job_id}" in resp.headers["location"]


# needed for mock_resend
from unittest.mock import MagicMock  # noqa: E402
