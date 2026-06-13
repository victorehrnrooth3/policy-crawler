"""Tests for the client-side title_keywords filter used on whole-company ATS boards."""

from __future__ import annotations

from policy_crawler.crawler.base import RawJob
from policy_crawler.crawler.run import _filter_by_title


def _job(title: str) -> RawJob:
    return RawJob(canonical_id=title, url="https://x/y", title=title)


def test_filter_keeps_matching_titles_case_insensitive() -> None:
    jobs = [
        _job("Counsel, AI Policy"),
        _job("Software Engineer, Backend"),
        _job("Public Policy Manager, Global Affairs"),
        _job("Senior Mechanical Engineer"),
    ]
    kept = _filter_by_title(jobs, ["policy", "affairs"])
    titles = {j.title for j in kept}
    assert titles == {"Counsel, AI Policy", "Public Policy Manager, Global Affairs"}


def test_filter_empty_keywords_via_caller_contract() -> None:
    # _filter_by_title with no keywords keeps nothing; callers guard with `if keywords`.
    jobs = [_job("Anything")]
    assert _filter_by_title(jobs, []) == []


def test_filter_handles_missing_title() -> None:
    j = RawJob(canonical_id="x", url="https://x/y", title="")
    assert _filter_by_title([j], ["policy"]) == []
