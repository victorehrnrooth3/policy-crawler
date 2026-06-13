from __future__ import annotations

import pytest

from policy_crawler.crawler.rippling import RipplingFetcher
from tests.crawler.conftest import make_source


@pytest.mark.vcr
def test_rippling_returns_jobs() -> None:
    source = make_source(
        name="Eurasia Group",
        careers_url="https://ats.rippling.com/eurasia-group/jobs",
        fetcher_kind="rippling",
        fetcher_config={"org": "eurasia-group"},
    )
    jobs = list(RipplingFetcher().fetch(source))
    assert len(jobs) >= 1
    job = jobs[0]
    assert job.canonical_id
    assert job.title
    assert job.url.startswith("http")


def test_rippling_missing_org_yields_nothing() -> None:
    source = make_source(fetcher_kind="rippling", fetcher_config={})
    jobs = list(RipplingFetcher().fetch(source))
    assert jobs == []
