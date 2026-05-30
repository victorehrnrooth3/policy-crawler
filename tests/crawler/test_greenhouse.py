from __future__ import annotations

import pytest

from policy_crawler.crawler.greenhouse import GreenhouseFetcher
from tests.crawler.conftest import make_source


@pytest.mark.vcr
def test_greenhouse_returns_jobs() -> None:
    source = make_source(
        name="Anthropic",
        careers_url="https://boards.greenhouse.io/anthropic",
        fetcher_kind="greenhouse",
        fetcher_config={"board": "anthropic"},
    )
    fetcher = GreenhouseFetcher()
    jobs = list(fetcher.fetch(source))
    assert len(jobs) >= 1
    job = jobs[0]
    assert job.canonical_id
    assert job.title
    assert job.url.startswith("http")


def test_greenhouse_missing_board_yields_nothing() -> None:
    source = make_source(fetcher_kind="greenhouse", fetcher_config={})
    jobs = list(GreenhouseFetcher().fetch(source))
    assert jobs == []
