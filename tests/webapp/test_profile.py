"""Tests for /profile routes — view, approve (opens PR), reject."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.webapp.conftest import _make_mock_conn


def _mock_change(**kwargs: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "diff": {"ops": [{"op": "add", "path": "soft_negatives[+]", "value": "x", "reason": "r"}]},
        "rationale_per_change": {
            "per_op": [{"op": "add", "path": "soft_negatives[+]", "reason": "r"}]
        },
        "status": "pending",
        "proposed_at": datetime.now(tz=UTC),
    }
    defaults.update(kwargs)
    return defaults


def test_profile_requires_auth(client: TestClient) -> None:
    assert client.get("/profile").status_code == 401


def test_profile_view_shows_pending_change(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    conn = _make_mock_conn(rows=[_mock_change()])
    with patch("policy_crawler.webapp.routes.profile.connection", return_value=conn):
        resp = client.get("/profile", cookies=auth_cookies)
    assert resp.status_code == 200
    assert "soft_negatives" in resp.text


def test_approve_change_opens_pr(
    client: TestClient, auth_cookies: dict[str, str], csrf_cookies: dict[str, str]
) -> None:
    change_id = uuid4()
    with patch(
        "policy_crawler.self_update.run.apply_proposed", return_value="https://pr"
    ) as mock_apply:
        resp = client.post(
            f"/profile/changes/{change_id}/approve",
            data={"csrf_token": "test-csrf-token-abc123"},
            cookies={**auth_cookies, **csrf_cookies},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert "/profile" in resp.headers["location"]
    mock_apply.assert_called_once()
    assert mock_apply.call_args.args[0] == change_id


def test_approve_change_pr_failure_keeps_pending(
    client: TestClient, auth_cookies: dict[str, str], csrf_cookies: dict[str, str]
) -> None:
    change_id = uuid4()
    with patch(
        "policy_crawler.self_update.run.apply_proposed", side_effect=RuntimeError("github 403")
    ):
        resp = client.post(
            f"/profile/changes/{change_id}/approve",
            data={"csrf_token": "test-csrf-token-abc123"},
            cookies={**auth_cookies, **csrf_cookies},
            follow_redirects=False,
        )

    assert resp.status_code == 502
    assert "github 403" in resp.text


def test_approve_change_csrf_required(client: TestClient, auth_cookies: dict[str, str]) -> None:
    resp = client.post(
        f"/profile/changes/{uuid4()}/approve",
        data={"csrf_token": "wrong"},
        cookies=auth_cookies,
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_reject_change_flow(
    client: TestClient, auth_cookies: dict[str, str], csrf_cookies: dict[str, str]
) -> None:
    conn = _make_mock_conn(rows=[])
    with patch("policy_crawler.webapp.routes.profile.connection", return_value=conn):
        resp = client.post(
            f"/profile/changes/{uuid4()}/reject",
            data={"csrf_token": "test-csrf-token-abc123"},
            cookies={**auth_cookies, **csrf_cookies},
            follow_redirects=False,
        )
    assert resp.status_code == 303
