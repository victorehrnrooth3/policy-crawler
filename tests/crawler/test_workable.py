from __future__ import annotations

from policy_crawler.crawler.workable import WorkableFetcher, _format_location
from tests.crawler.conftest import make_source


def test_format_location_handles_dict() -> None:
    loc = {"city": "Milton Keynes", "region": "England", "country": "United Kingdom"}
    assert _format_location(loc) == "Milton Keynes, England, United Kingdom"


def test_format_location_handles_string() -> None:
    assert _format_location("London, UK") == "London, UK"


def test_format_location_handles_none_and_empty() -> None:
    assert _format_location(None) is None
    assert _format_location({}) is None
    assert _format_location("") is None


def test_workable_missing_subdomain_yields_nothing() -> None:
    source = make_source(fetcher_kind="workable", fetcher_config={})
    jobs = list(WorkableFetcher().fetch(source))
    assert jobs == []
