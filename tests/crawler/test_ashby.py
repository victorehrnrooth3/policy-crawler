from __future__ import annotations

import pytest

from policy_crawler.crawler.ashby import AshbyFetcher
from tests.crawler.conftest import make_source


@pytest.mark.vcr
def test_ashby_returns_jobs() -> None:
    source = make_source(
        name="Ashby",
        careers_url="https://jobs.ashbyhq.com/ashby",
        fetcher_kind="ashby",
        fetcher_config={"org": "ashby"},
    )
    fetcher = AshbyFetcher()
    jobs = list(fetcher.fetch(source))
    assert len(jobs) >= 1
    job = jobs[0]
    assert job.canonical_id
    assert job.title
    assert job.url.startswith("http")


def test_ashby_missing_org_yields_nothing() -> None:
    source = make_source(fetcher_kind="ashby", fetcher_config={})
    jobs = list(AshbyFetcher().fetch(source))
    assert jobs == []
