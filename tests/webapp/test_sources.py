"""Tests for /sources routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.webapp.conftest import _make_mock_conn


def _mock_source(**kwargs: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "name": "Test Think Tank",
        "careers_url": "https://ttt.org/careers",
        "category": "think_tank",
        "fetcher_kind": "greenhouse",
        "priority": 3,
        "enabled": True,
        "last_checked_at": None,
        "last_success_at": None,
    }
    defaults.update(kwargs)
    return defaults


def _mock_suggestion(**kwargs: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "name": "Suggested Org",
        "careers_url": "https://suggested.org/jobs",
        "category": "think_tank",
        "fetcher_kind": "greenhouse",
        "rationale": "Good fit for policy roles.",
        "status": "pending",
        "proposed_at": datetime.now(tz=UTC),
    }
    defaults.update(kwargs)
    return defaults


# ── GET /sources ──────────────────────────────────────────────────────────────


def test_sources_requires_auth(client: TestClient) -> None:
    resp = client.get("/sources")
    assert resp.status_code == 401


def test_sources_shows_active_tab(client: TestClient, auth_cookies: dict[str, str]) -> None:
    sources = [_mock_source(name="Brookings"), _mock_source(name="RAND")]
    conn = _make_mock_conn(rows=sources)
    conn.__enter__.return_value.cursor.return_value.fetchall.side_effect = [
        sources,  # active sources
        [],  # pending suggestions
        [],  # rejected suggestions
    ]

    with patch("policy_crawler.webapp.routes.sources.connection", return_value=conn):
        resp = client.get("/sources?tab=active", cookies=auth_cookies)

    assert resp.status_code == 200
    assert "Brookings" in resp.text
    assert "RAND" in resp.text


def test_sources_shows_pending_tab(client: TestClient, auth_cookies: dict[str, str]) -> None:
    suggestions = [
        _mock_suggestion(name="New Policy Org", rationale="Great org for climate policy.")
    ]
    conn = _make_mock_conn(rows=[])
    conn.__enter__.return_value.cursor.return_value.fetchall.side_effect = [
        [],  # active sources
        suggestions,  # pending
        [],  # rejected
    ]

    with patch("policy_crawler.webapp.routes.sources.connection", return_value=conn):
        resp = client.get("/sources?tab=pending", cookies=auth_cookies)

    assert resp.status_code == 200
    assert "New Policy Org" in resp.text
    assert "Great org for climate policy" in resp.text


# ── POST /sources/suggested/{id}/approve ─────────────────────────────────────


def test_approve_suggestion_requires_auth(client: TestClient, csrf_cookies: dict[str, str]) -> None:
    resp = client.post(
        f"/sources/suggested/{uuid4()}/approve",
        data={"csrf_token": "test-csrf-token-abc123"},
        cookies=csrf_cookies,
        follow_redirects=False,
    )
    assert resp.status_code in (401, 303)


def test_approve_suggestion_csrf_required(client: TestClient, auth_cookies: dict[str, str]) -> None:
    resp = client.post(
        f"/sources/suggested/{uuid4()}/approve",
        data={"csrf_token": "wrong"},
        cookies=auth_cookies,
    )
    assert resp.status_code == 403


def test_approve_suggestion_flow(
    client: TestClient, auth_cookies: dict[str, str], csrf_cookies: dict[str, str]
) -> None:
    suggestion_id = uuid4()
    conn = _make_mock_conn(rows=[_mock_suggestion(id=suggestion_id)])

    with patch("policy_crawler.webapp.routes.sources.connection", return_value=conn):
        resp = client.post(
            f"/sources/suggested/{suggestion_id}/approve",
            data={"csrf_token": "test-csrf-token-abc123"},
            cookies={**auth_cookies, **csrf_cookies},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert "/sources" in resp.headers["location"]


def test_reject_suggestion_flow(
    client: TestClient, auth_cookies: dict[str, str], csrf_cookies: dict[str, str]
) -> None:
    suggestion_id = uuid4()
    conn = _make_mock_conn(rows=[])

    with patch("policy_crawler.webapp.routes.sources.connection", return_value=conn):
        resp = client.post(
            f"/sources/suggested/{suggestion_id}/reject",
            data={"csrf_token": "test-csrf-token-abc123"},
            cookies={**auth_cookies, **csrf_cookies},
            follow_redirects=False,
        )

    assert resp.status_code == 303


def test_snooze_suggestion_flow(
    client: TestClient, auth_cookies: dict[str, str], csrf_cookies: dict[str, str]
) -> None:
    suggestion_id = uuid4()
    conn = _make_mock_conn(rows=[])

    with patch("policy_crawler.webapp.routes.sources.connection", return_value=conn):
        resp = client.post(
            f"/sources/suggested/{suggestion_id}/snooze",
            data={"csrf_token": "test-csrf-token-abc123"},
            cookies={**auth_cookies, **csrf_cookies},
            follow_redirects=False,
        )

    assert resp.status_code == 303


# ── GET /status (no auth) ─────────────────────────────────────────────────────


def test_status_no_auth_required(client: TestClient) -> None:
    conn = _make_mock_conn(rows=[])
    conn.__enter__.return_value.cursor.return_value.fetchall.side_effect = [
        [],  # runs
        [],  # llm_stats
        [],  # sources
    ]
    conn.__enter__.return_value.cursor.return_value.fetchone.side_effect = [
        {"total": 42},
        {"total": 30},
    ]

    with patch("policy_crawler.webapp.routes.status.connection", return_value=conn):
        resp = client.get("/status")

    assert resp.status_code == 200
    assert "42" in resp.text  # job_count
    assert "30" in resp.text  # scored_count


def test_status_shows_runs(client: TestClient) -> None:
    from datetime import timedelta

    now = datetime.now(tz=UTC)
    runs = [
        {
            "id": uuid4(),
            "kind": "daily",
            "status": "succeeded",
            "started_at": now - timedelta(hours=1),
            "finished_at": now,
            "jobs_seen": 100,
            "jobs_new": 5,
            "llm_calls_count": 10,
            "total_cost_usd": 0.05,
            "error": None,
        }
    ]
    conn = _make_mock_conn(rows=[])
    conn.__enter__.return_value.cursor.return_value.fetchall.side_effect = [
        runs,
        [],
        [],
    ]
    conn.__enter__.return_value.cursor.return_value.fetchone.side_effect = [
        {"total": 100},
        {"total": 80},
    ]

    with patch("policy_crawler.webapp.routes.status.connection", return_value=conn):
        resp = client.get("/status")

    assert resp.status_code == 200
    assert "daily" in resp.text
    assert "succeeded" in resp.text


# ── CSRF protection on POSTs ─────────────────────────────────────────────────


def test_csrf_protection_on_all_source_post_endpoints(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    endpoints = [
        f"/sources/suggested/{uuid4()}/approve",
        f"/sources/suggested/{uuid4()}/reject",
        f"/sources/suggested/{uuid4()}/snooze",
    ]
    for url in endpoints:
        resp = client.post(url, data={"csrf_token": ""}, cookies=auth_cookies)
        assert resp.status_code == 403, f"Expected 403 for {url}"
