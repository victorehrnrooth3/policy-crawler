from __future__ import annotations

import pytest

from policy_crawler.crawler.lever import LeverFetcher
from tests.crawler.conftest import make_source


@pytest.mark.vcr
def test_lever_returns_jobs() -> None:
    source = make_source(
        name="Palantir Technologies",
        careers_url="https://api.lever.co/v0/postings/palantir",
        fetcher_kind="lever",
        fetcher_config={"company": "palantir"},
    )
    fetcher = LeverFetcher()
    jobs = list(fetcher.fetch(source))
    assert len(jobs) >= 1
    job = jobs[0]
    assert job.canonical_id
    assert job.title
    assert job.url.startswith("http")


def test_lever_missing_company_yields_nothing() -> None:
    source = make_source(fetcher_kind="lever", fetcher_config={})
    jobs = list(LeverFetcher().fetch(source))
    assert jobs == []
