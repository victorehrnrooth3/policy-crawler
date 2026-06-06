"""Tests for digest/compose.py — job selection and mark-sent logic with mocked DB."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest


def _make_job(
    *,
    job_id: UUID | None = None,
    pass1_score: int = 75,
    pass1_confidence: str = "med",
    pass2_score: int | None = 80,
    dealbreaker_hits: list[str] | None = None,
    posting_type: str = "role",
    pass1_reason: str = "Good match.",
    pass2_reason: str | None = "Strong fit.",
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        "id": job_id or uuid4(),
        "title": "Policy Analyst",
        "company": "Test Org",
        "location_raw": "London",
        "url": "https://example.com/job/1",
        "posting_type": posting_type,
        "pass1_score": pass1_score,
        "pass1_confidence": pass1_confidence,
        "pass1_dealbreaker_hits": dealbreaker_hits if dealbreaker_hits is not None else [],
        "pass1_reason": pass1_reason,
        "pass2_score": pass2_score,
        "pass2_reason_to_consider": pass2_reason,
        "pass2_concerns": None,
        "pass2_matched_signals": [],
        "pass2_missing_info": [],
        "pass2_recommended_action": "apply_now",
        **kwargs,
    }


def _mock_connection(rows: list[dict[str, Any]]) -> MagicMock:
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = rows

    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur

    return conn


def test_pick_jobs_returns_top_k() -> None:
    from policy_crawler.digest.compose import pick_jobs

    jobs = [_make_job(pass2_score=90 - i * 5) for i in range(12)]
    with patch("policy_crawler.digest.compose.connection", return_value=_mock_connection(jobs)):
        result = pick_jobs(date.today(), k_top=8, k_borderline=2)

    top = [j for j in result if not j["_borderline"]]
    assert len(top) == 8
    assert top[0]["pass2_score"] == 90  # highest first


def test_pick_jobs_borderline_detected() -> None:
    from policy_crawler.digest.compose import pick_jobs

    top_jobs = [_make_job(pass2_score=80 - i * 5) for i in range(8)]
    borderline_job = _make_job(
        pass1_score=50, pass1_confidence="low", pass2_score=None, pass2_reason=None
    )
    rows = top_jobs + [borderline_job]

    with patch("policy_crawler.digest.compose.connection", return_value=_mock_connection(rows)):
        result = pick_jobs(date.today(), k_top=8, k_borderline=2)

    borderline = [j for j in result if j["_borderline"]]
    assert len(borderline) == 1


def test_pick_jobs_borderline_outside_score_range_not_included() -> None:
    from policy_crawler.digest.compose import pick_jobs

    top_jobs = [_make_job(pass2_score=80 - i * 5) for i in range(8)]
    # pass1_score=30 is below the [40,60] range
    low_score_job = _make_job(
        pass1_score=30, pass1_confidence="low", pass2_score=None, pass2_reason=None
    )
    rows = top_jobs + [low_score_job]

    with patch("policy_crawler.digest.compose.connection", return_value=_mock_connection(rows)):
        result = pick_jobs(date.today())

    borderline = [j for j in result if j["_borderline"]]
    assert len(borderline) == 0


def test_pick_jobs_borderline_capped_at_k() -> None:
    from policy_crawler.digest.compose import pick_jobs

    top_jobs = [_make_job(pass2_score=80 - i * 5) for i in range(8)]
    borderline_jobs = [
        _make_job(pass1_score=50, pass1_confidence="low", pass2_score=None, pass2_reason=None)
        for _ in range(5)
    ]
    rows = top_jobs + borderline_jobs

    with patch("policy_crawler.digest.compose.connection", return_value=_mock_connection(rows)):
        result = pick_jobs(date.today(), k_top=8, k_borderline=2)

    borderline = [j for j in result if j["_borderline"]]
    assert len(borderline) == 2


def test_pick_jobs_empty_returns_empty() -> None:
    from policy_crawler.digest.compose import pick_jobs

    with patch("policy_crawler.digest.compose.connection", return_value=_mock_connection([])):
        result = pick_jobs(date.today())

    assert result == []


def test_pick_jobs_marks_borderline_flag() -> None:
    from policy_crawler.digest.compose import pick_jobs

    top_job = _make_job(pass2_score=85)
    borderline_job = _make_job(
        pass1_score=55, pass1_confidence="low", pass2_score=None, pass2_reason=None
    )

    with patch(
        "policy_crawler.digest.compose.connection",
        return_value=_mock_connection([top_job, borderline_job]),
    ):
        result = pick_jobs(date.today(), k_top=1, k_borderline=1)

    assert result[0]["_borderline"] is False
    assert result[1]["_borderline"] is True


def test_mark_digest_sent_no_op_on_empty() -> None:
    from policy_crawler.digest.compose import mark_digest_sent

    conn = _mock_connection([])
    with patch("policy_crawler.digest.compose.connection", return_value=conn):
        mark_digest_sent([])

    conn.cursor.assert_not_called()


def test_mark_digest_sent_executes_update() -> None:
    from policy_crawler.digest.compose import mark_digest_sent

    conn = _mock_connection([])
    ids = [uuid4(), uuid4()]
    with patch("policy_crawler.digest.compose.connection", return_value=conn):
        mark_digest_sent(ids)

    cur = conn.cursor.return_value.__enter__.return_value
    cur.execute.assert_called_once()
    call_args = cur.execute.call_args[0]
    assert call_args[1] == (ids,)


@pytest.mark.skipif(
    not __import__("os").environ.get("NEON_DATABASE_URL"),
    reason="NEON_DATABASE_URL not set; skipping live DB test",
)
def test_pick_jobs_live_smoke() -> None:
    from policy_crawler.digest.compose import pick_jobs

    result = pick_jobs(date.today(), k_top=3, k_borderline=1)
    assert isinstance(result, list)
    for job in result:
        assert "id" in job
        assert "_borderline" in job
