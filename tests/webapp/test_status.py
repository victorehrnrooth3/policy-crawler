"""Tests for the /status page and /status.json — DB + spend mocked, no auth required."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _mock_conn(
    runs: list[Any], llm_stats: list[Any], sources: list[Any], counts: list[dict[str, Any]]
) -> MagicMock:
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.side_effect = [runs, llm_stats, sources]
    cur.fetchone.side_effect = counts
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    return conn


def _run_row(**kw: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "id": "r1",
        "kind": "weekly",
        "status": "succeeded",
        "started_at": now - timedelta(minutes=10),
        "finished_at": now,
        "jobs_seen": 50,
        "jobs_new": 12,
        "llm_calls_count": 70,
        "total_cost_usd": 0.42,
        "error": None,
    }
    base.update(kw)
    return base


def _source_row(name: str, gap_days: int | None) -> dict[str, Any]:
    last = None if gap_days is None else datetime.now(UTC) - timedelta(days=gap_days)
    return {
        "name": name,
        "category": "think_tank",
        "fetcher_kind": "camoufox",
        "enabled": True,
        "last_checked_at": last,
        "last_success_at": last,
    }


_COUNTS = [
    {"n": 3},  # pending suggested sources
    {"n": 1},  # pending profile changes
    {"total": 100},  # job_count
    {"total": 80},  # scored_count
]


def _patch_spend() -> Any:
    return patch.multiple(
        "policy_crawler.webapp.routes.status",
        daily_spend=lambda day: 0.05,
        monthly_spend=lambda month: 1.5,
    )


def test_status_page_renders(client: TestClient) -> None:
    conn = _mock_conn(
        runs=[_run_row()],
        llm_stats=[],
        sources=[_source_row("Brookings", 0), _source_row("RAND", 5), _source_row("Stale", None)],
        counts=list(_COUNTS),
    )
    with patch("policy_crawler.webapp.routes.status.connection", return_value=conn), _patch_spend():
        resp = client.get("/status")

    assert resp.status_code == 200
    assert "Brookings" in resp.text
    assert "RAND" in resp.text
    assert "5d" in resp.text  # overdue gap rendered
    assert "never" in resp.text  # source that never succeeded
    assert "3 suggested source" in resp.text
    assert "1 profile change" in resp.text


def test_status_page_no_auth_required(client: TestClient) -> None:
    conn = _mock_conn(runs=[], llm_stats=[], sources=[], counts=list(_COUNTS))
    with patch("policy_crawler.webapp.routes.status.connection", return_value=conn), _patch_spend():
        resp = client.get("/status")  # no cookies
    assert resp.status_code == 200


def test_status_json(client: TestClient) -> None:
    conn = _mock_conn(
        runs=[_run_row()],
        llm_stats=[],
        sources=[_source_row("Stale", 9), _source_row("Fresh", 0)],
        counts=list(_COUNTS),
    )
    with patch("policy_crawler.webapp.routes.status.connection", return_value=conn), _patch_spend():
        resp = client.get("/status.json")

    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_sources"] == 3
    assert data["pending_changes"] == 1
    assert data["daily_spend_usd"] == 0.05
    assert data["sources_overdue"] == 1  # only the 9d source is > 3d
    assert data["last_run"]["kind"] == "weekly"
