"""Tests for ranker/run.py — orchestration, DB writes, cost caps (mocked Anthropic + DB)."""

from __future__ import annotations

import os
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from policy_crawler.ranker.pass1 import Pass1Result
from policy_crawler.ranker.pass2 import Pass2Result
from policy_crawler.ranker.prompts import SYSTEM_PROMPT, format_recent_feedback
from policy_crawler.ranker.run import MAX_PASS1_PER_RUN, MAX_PASS2_PER_RUN, RankerSummary


def _run_write_capture(write_fn: Any, results: list[Any]) -> MagicMock:
    """Run a _write_*_results fn with execute_write faked, return the mock cursor.

    The write functions now route through db.execute_write(work); we fake that to
    run `work(conn)` once against a mock connection so tests can inspect the
    cursor's execute calls.
    """
    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    def fake_execute_write(work: Any, **_kw: Any) -> None:
        work(mock_conn)

    with patch("policy_crawler.ranker.run.execute_write", fake_execute_write):
        write_fn(results, run_id=None)
    return mock_cur


# ── format_recent_feedback (no DB, no mocking needed) ─────────────────────────


def test_format_recent_feedback_empty() -> None:
    assert format_recent_feedback([]) == ""


def test_format_recent_feedback_formats_correctly() -> None:
    votes = [
        {"vote": "up", "title": "Energy Analyst", "company": "RFF", "freetext": "Exactly right"},
        {"vote": "down", "title": "IB Analyst", "company": "GS", "freetext": None},
    ]
    text = format_recent_feedback(votes)
    assert "[UP]" in text
    assert "RFF" in text
    assert "[DOWN]" in text
    assert "Exactly right" in text


def test_format_recent_feedback_respects_max_entries() -> None:
    votes = [
        {"vote": "up", "title": f"Job {i}", "company": "Co", "freetext": None} for i in range(20)
    ]
    text = format_recent_feedback(votes, max_entries=5)
    assert text.count("[UP]") == 5


# ── RankerSummary dataclass ────────────────────────────────────────────────────


def test_ranker_summary_defaults() -> None:
    s = RankerSummary()
    assert s.pass1_scored == 0
    assert s.pass2_scored == 0
    assert s.total_cost_usd == 0.0
    assert s.errors == []


def test_ranker_summary_accumulates() -> None:
    s = RankerSummary()
    s.pass1_scored = 15
    s.pass2_scored = 5
    s.total_cost_usd = 0.025
    assert s.pass1_scored == 15
    assert s.pass2_scored == 5


# ── SYSTEM_PROMPT content check ────────────────────────────────────────────────


def test_system_prompt_includes_dealbreaker_instruction() -> None:
    assert "dealbreaker" in SYSTEM_PROMPT.lower() or "≤ 30" in SYSTEM_PROMPT
    assert "tool" in SYSTEM_PROMPT.lower()


# ── Pass cap constants ────────────────────────────────────────────────────────


def test_pass1_cap_is_reasonable() -> None:
    assert 10 <= MAX_PASS1_PER_RUN <= 1_000


def test_pass2_cap_is_less_than_pass1_cap() -> None:
    assert MAX_PASS2_PER_RUN < MAX_PASS1_PER_RUN


# ── score_pending with mocked DB and Anthropic ────────────────────────────────


def _make_pass1_result(job_id: uuid.UUID, score: int = 72, confidence: str = "high") -> Pass1Result:
    return Pass1Result(
        job_id=job_id,
        fit_score=score,
        confidence=confidence,
        posting_type="role",
        geography_match="secondary",
        dealbreaker_hits=[],
        screen_reason="Good topic match.",
        input_tokens=200,
        output_tokens=80,
        cost_usd=0.0006,
    )


def _make_pass2_result(
    job_id: uuid.UUID, score: int = 80, action: str = "apply_now"
) -> Pass2Result:
    return Pass2Result(
        job_id=job_id,
        fit_score=score,
        reason_to_consider="Strong fit.",
        concerns="Minor location concern.",
        matched_signals=["energy policy"],
        missing_info=["visa policy"],
        recommended_action=action,
        input_tokens=600,
        output_tokens=200,
        cost_usd=0.0048,
    )


def _make_db_job_row(
    job_id: uuid.UUID | None = None, pass1_score: int | None = None
) -> dict[str, Any]:
    return {
        "id": job_id or uuid.uuid4(),
        "source_id": uuid.uuid4(),
        "title": "Research Analyst",
        "company": "Brookings",
        "location_raw": "DC",
        "posting_type": "role",
        "description_clean": "Energy policy research.",
        "description_raw": "Energy policy research.",
        "pass1_score": pass1_score,
        "pass1_confidence": "high" if pass1_score else None,
        "source_priority": 3,
    }


@pytest.mark.skipif(
    not os.environ.get("NEON_DATABASE_URL"),
    reason="NEON_DATABASE_URL not set; skipping live DB test",
)
def test_score_pending_live_smoke() -> None:
    """Minimal smoke test: score_pending runs without error on a real DB (limit=1)."""
    from policy_crawler.ranker.run import score_pending

    summary = score_pending(limit=1)
    assert isinstance(summary, RankerSummary)
    # Either scored some jobs or 0 if DB already fully scored
    assert summary.pass1_scored >= 0
    assert summary.total_cost_usd >= 0.0


def test_score_pending_no_anthropic_key_raises(monkeypatch) -> None:
    """score_pending raises RuntimeError when ANTHROPIC_API_KEY is missing."""
    from policy_crawler.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    try:
        from policy_crawler.ranker.run import score_pending

        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            score_pending(limit=1)
    finally:
        get_settings.cache_clear()


def test_write_pass1_results_skips_total_failures() -> None:
    """_write_pass1_results should skip results with error and score==0 and no reason."""
    from policy_crawler.ranker.run import _write_pass1_results

    error_result = Pass1Result(
        job_id=uuid.uuid4(),
        fit_score=0,
        confidence="low",
        posting_type="unknown",
        geography_match="unknown",
        dealbreaker_hits=[],
        screen_reason="",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        error="API timeout",
    )

    mock_cur = _run_write_capture(_write_pass1_results, [error_result])
    mock_cur.execute.assert_not_called()


def test_write_pass1_results_persists_valid_result() -> None:
    """_write_pass1_results should call execute for a valid result."""
    from policy_crawler.ranker.run import _write_pass1_results

    valid_result = _make_pass1_result(uuid.uuid4())
    mock_cur = _run_write_capture(_write_pass1_results, [valid_result])
    assert mock_cur.execute.call_count == 2  # UPDATE jobs + INSERT llm_calls


def test_write_pass2_results_skips_total_failures() -> None:
    from policy_crawler.ranker.run import _write_pass2_results

    error_result = Pass2Result(
        job_id=uuid.uuid4(),
        fit_score=0,
        reason_to_consider="",
        concerns="",
        matched_signals=[],
        missing_info=[],
        recommended_action="needs_human_review",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        error="API error",
    )

    mock_cur = _run_write_capture(_write_pass2_results, [error_result])
    mock_cur.execute.assert_not_called()
