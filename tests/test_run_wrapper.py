"""Tests for the run.py top-level orchestrator."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _clear_settings(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    from policy_crawler.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("NEON_DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("TOKEN_HMAC_SECRET", "test-hmac-secret-at-least-32bytes!!")
    yield
    get_settings.cache_clear()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_crawl_summary(jobs_seen: int = 5, jobs_new: int = 2) -> MagicMock:
    m = MagicMock()
    m.jobs_seen = jobs_seen
    m.jobs_new = jobs_new
    m.errors = []
    return m


def _mock_rank_summary(p1: int = 3, p2: int = 1, cost: float = 0.01) -> MagicMock:
    m = MagicMock()
    m.pass1_scored = p1
    m.pass2_scored = p2
    m.total_cost_usd = cost
    return m


# ── Order and plumbing ────────────────────────────────────────────────────────


def test_daily_invokes_crawler_ranker_digest_in_order() -> None:
    run_id = uuid4()
    call_order: list[str] = []

    crawl_result = _mock_crawl_summary()
    rank_result = _mock_rank_summary()

    def _track(name: str, ret: object):
        def _fn(*_a: object, **_kw: object) -> object:
            call_order.append(name)
            return ret

        return _fn

    with (
        patch("policy_crawler.run.start_run", return_value=run_id),
        patch("policy_crawler.run.finish_run"),
        patch("policy_crawler.crawler.run.crawl_all", side_effect=_track("crawl", crawl_result)),
        patch("policy_crawler.ranker.run.score_pending", side_effect=_track("rank", rank_result)),
        patch("policy_crawler.digest.send.send_digest", side_effect=_track("digest", None)),
    ):
        from policy_crawler.run import run

        run("daily")

    assert call_order == ["crawl", "rank", "digest"]


def test_daily_opens_and_closes_run_row() -> None:
    run_id = uuid4()
    crawl_result = _mock_crawl_summary(jobs_seen=5, jobs_new=2)
    rank_result = _mock_rank_summary(p1=3, p2=1, cost=0.01)

    with (
        patch("policy_crawler.run.start_run", return_value=run_id) as mock_start,
        patch("policy_crawler.run.finish_run") as mock_finish,
        patch("policy_crawler.crawler.run.crawl_all", return_value=crawl_result),
        patch("policy_crawler.ranker.run.score_pending", return_value=rank_result),
        patch("policy_crawler.digest.send.send_digest"),
    ):
        from policy_crawler.run import run

        run("daily")

    mock_start.assert_called_once_with("daily")
    mock_finish.assert_called_once_with(
        run_id,
        status="succeeded",
        jobs_seen=5,
        jobs_new=2,
        llm_calls_count=4,
        total_cost_usd=0.01,
    )


# ── Exception handling ────────────────────────────────────────────────────────


def test_exception_in_crawler_still_closes_run_row() -> None:
    run_id = uuid4()

    with (
        patch("policy_crawler.run.start_run", return_value=run_id),
        patch("policy_crawler.run.finish_run") as mock_finish,
        patch("policy_crawler.crawler.run.crawl_all", side_effect=RuntimeError("crawl boom")),
        patch("policy_crawler.run._send_failure_alert"),
    ):
        from policy_crawler.run import run

        with pytest.raises(RuntimeError, match="crawl boom"):
            run("daily")

    mock_finish.assert_called_once()
    assert mock_finish.call_args.kwargs["status"] == "failed"
    assert "crawl boom" in mock_finish.call_args.kwargs["error"]


def test_exception_in_ranker_still_closes_run_row() -> None:
    run_id = uuid4()
    crawl_result = _mock_crawl_summary()

    with (
        patch("policy_crawler.run.start_run", return_value=run_id),
        patch("policy_crawler.run.finish_run") as mock_finish,
        patch("policy_crawler.crawler.run.crawl_all", return_value=crawl_result),
        patch("policy_crawler.ranker.run.score_pending", side_effect=RuntimeError("rank boom")),
        patch("policy_crawler.run._send_failure_alert"),
    ):
        from policy_crawler.run import run

        with pytest.raises(RuntimeError, match="rank boom"):
            run("daily")

    assert mock_finish.call_args.kwargs["status"] == "failed"


def test_exception_sends_failure_alert() -> None:
    run_id = uuid4()

    with (
        patch("policy_crawler.run.start_run", return_value=run_id),
        patch("policy_crawler.run.finish_run"),
        patch("policy_crawler.crawler.run.crawl_all", side_effect=RuntimeError("boom")),
        patch("policy_crawler.run._send_failure_alert") as mock_alert,
    ):
        from policy_crawler.run import run

        with pytest.raises(RuntimeError):
            run("daily")

    mock_alert.assert_called_once_with("daily", "boom")


# ── Weekly stubs open / close runs rows too ───────────────────────────────────


def test_weekly_discovery_opens_and_closes_run_row() -> None:
    run_id = uuid4()

    with (
        patch("policy_crawler.run.start_run", return_value=run_id) as mock_start,
        patch("policy_crawler.run.finish_run") as mock_finish,
    ):
        from policy_crawler.run import run

        run("weekly_discovery")

    mock_start.assert_called_once_with("weekly_discovery")
    mock_finish.assert_called_once()
    assert mock_finish.call_args.kwargs["status"] == "succeeded"


def test_weekly_self_update_opens_and_closes_run_row() -> None:
    run_id = uuid4()

    with (
        patch("policy_crawler.run.start_run", return_value=run_id) as mock_start,
        patch("policy_crawler.run.finish_run") as mock_finish,
    ):
        from policy_crawler.run import run

        run("weekly_self_update", gh_pat="ghp_test")

    mock_start.assert_called_once_with("weekly_self_update")
    mock_finish.assert_called_once()
    assert mock_finish.call_args.kwargs["status"] == "succeeded"
