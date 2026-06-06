"""Tests for /inbox routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.webapp.conftest import _make_mock_conn


def _mock_job(**kwargs: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "title": "Policy Analyst",
        "company": "Think Tank Ltd",
        "location_raw": "London, UK",
        "url": "https://example.com/jobs/1",
        "posting_type": "role",
        "pass1_score": 70,
        "pass1_confidence": "high",
        "pass2_score": 80,
        "pass2_reason_to_consider": "Strong policy focus.",
        "pass2_concerns": None,
        "pass2_recommended_action": "apply_now",
        "digest_sent_at": datetime.now(tz=UTC),
        "first_seen_at": datetime.now(tz=UTC),
        "source_name": "Test Source",
        "source_category": "think_tank",
    }
    defaults.update(kwargs)
    return defaults


# ── /inbox ────────────────────────────────────────────────────────────────────


def test_inbox_requires_auth(client: TestClient) -> None:
    resp = client.get("/inbox")
    assert resp.status_code == 401


def test_inbox_returns_jobs(client: TestClient, auth_cookies: dict[str, str]) -> None:
    jobs = [_mock_job(title="Climate Researcher"), _mock_job(title="Energy Policy Lead")]
    conn = _make_mock_conn(rows=jobs)

    with patch("policy_crawler.webapp.routes.inbox.connection", return_value=conn):
        resp = client.get("/inbox", cookies=auth_cookies)

    assert resp.status_code == 200
    assert "Climate Researcher" in resp.text
    assert "Energy Policy Lead" in resp.text


def test_inbox_empty_state(client: TestClient, auth_cookies: dict[str, str]) -> None:
    conn = _make_mock_conn(rows=[])

    with patch("policy_crawler.webapp.routes.inbox.connection", return_value=conn):
        resp = client.get("/inbox", cookies=auth_cookies)

    assert resp.status_code == 200
    assert "no jobs" in resp.text.lower() or "match" in resp.text.lower()


def test_inbox_score_shown(client: TestClient, auth_cookies: dict[str, str]) -> None:
    jobs = [_mock_job(pass2_score=87)]
    conn = _make_mock_conn(rows=jobs)

    with patch("policy_crawler.webapp.routes.inbox.connection", return_value=conn):
        resp = client.get("/inbox", cookies=auth_cookies)

    assert resp.status_code == 200
    assert "87" in resp.text


# ── /inbox/{job_id} ───────────────────────────────────────────────────────────


def test_inbox_detail_requires_auth(client: TestClient) -> None:
    resp = client.get(f"/inbox/{uuid4()}")
    assert resp.status_code == 401


def test_inbox_detail_shows_job(client: TestClient, auth_cookies: dict[str, str]) -> None:
    job = _mock_job(
        title="Nuclear Policy Director",
        company="Atoms Inc",
        pass2_reason_to_consider="Unique expertise in nuclear governance.",
        description_clean="Full job description here.",
    )
    job["pass2_matched_signals"] = ["nuclear policy", "governance"]
    job["pass2_missing_info"] = []
    job["pass1_reason"] = "Good match."
    job["pass1_dealbreaker_hits"] = []
    job["source_url"] = "https://atomsinc.com/careers"
    job["remote_policy"] = "hybrid"
    job["seniority"] = "senior"
    job["compensation"] = None

    conn = _make_mock_conn(rows=[job])

    # fetchall for feedbacks returns empty
    conn.__enter__.return_value.cursor.return_value.fetchall.side_effect = [job, []]

    with patch("policy_crawler.webapp.routes.inbox.connection", return_value=conn):
        resp = client.get(f"/inbox/{job['id']}", cookies=auth_cookies)

    assert resp.status_code == 200
    assert "Nuclear Policy Director" in resp.text
    assert "Atoms Inc" in resp.text


def test_inbox_detail_not_found(client: TestClient, auth_cookies: dict[str, str]) -> None:
    conn = _make_mock_conn(rows=[None])
    conn.__enter__.return_value.cursor.return_value.fetchone.return_value = None

    with patch("policy_crawler.webapp.routes.inbox.connection", return_value=conn):
        resp = client.get(f"/inbox/{uuid4()}", cookies=auth_cookies)

    assert resp.status_code == 404


# ── POST /inbox/{job_id}/feedback ─────────────────────────────────────────────


def test_inbox_feedback_csrf_required(client: TestClient, auth_cookies: dict[str, str]) -> None:
    resp = client.post(
        f"/inbox/{uuid4()}/feedback",
        data={"freetext": "test", "csrf_token": "wrong"},
        cookies=auth_cookies,
    )
    assert resp.status_code == 403


def test_inbox_feedback_redirects_after_save(
    client: TestClient, auth_cookies: dict[str, str], csrf_cookies: dict[str, str]
) -> None:
    job_id = uuid4()
    conn = _make_mock_conn(rows=[])

    with patch("policy_crawler.webapp.routes.inbox.connection", return_value=conn):
        resp = client.post(
            f"/inbox/{job_id}/feedback",
            data={"freetext": "Interesting!", "csrf_token": "test-csrf-token-abc123"},
            cookies={**auth_cookies, **csrf_cookies},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert f"/inbox/{job_id}" in resp.headers["location"]
