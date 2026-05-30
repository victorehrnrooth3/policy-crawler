from __future__ import annotations

import pytest

from policy_crawler.crawler.base import RawJob
from policy_crawler.crawler.normalize import (
    detect_posting_type,
    detect_remote_policy,
    detect_seniority,
    normalize,
    parse_location,
)
from tests.crawler.conftest import make_source


def raw(title: str = "Analyst", **kw: object) -> RawJob:
    return RawJob(canonical_id="x", url="https://example.com", title=title, **kw)  # type: ignore[arg-type]


# ── remote_policy ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("loc", "desc", "expected"),
    [
        ("London, UK", "", "unknown"),
        ("Remote", "", "remote"),
        ("San Francisco (Remote)", "", "remote"),
        ("New York (Hybrid)", "", "hybrid"),
        ("On-site only", "", "onsite"),
        ("Washington DC", "This is a fully remote role", "remote"),
    ],
)
def test_detect_remote_policy(loc: str, desc: str, expected: str) -> None:
    assert detect_remote_policy(loc, desc) == expected


# ── seniority ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Research Intern", "intern"),
        ("Junior Research Analyst", "early_career"),
        ("Senior Policy Advisor", "senior"),
        ("Director of Policy", "lead"),
        ("VP of Government Affairs", "lead"),
        ("Chief Strategy Officer", "exec"),
        ("Research Analyst", "mid"),
        ("Energy Economist", "mid"),
        ("Staff Engineer", "senior"),
        ("Associate Fellow", "early_career"),
    ],
)
def test_detect_seniority(title: str, expected: str) -> None:
    assert detect_seniority(title) == expected


# ── posting_type ────────────────────────────────────────────────────────────────


def test_posting_type_from_source_category_predoc() -> None:
    source = make_source(category="predoc_program")
    assert detect_posting_type(raw(), source) == "predoc"


def test_posting_type_from_source_category_phd() -> None:
    source = make_source(category="phd_program")
    assert detect_posting_type(raw(), source) == "program_call"


def test_posting_type_fellowship_title() -> None:
    source = make_source(category="think_tank")
    assert detect_posting_type(raw("Research Fellowship"), source) == "fellowship"


def test_posting_type_role_default() -> None:
    source = make_source(category="think_tank")
    assert detect_posting_type(raw("Economist"), source) == "role"


def test_posting_type_explicit_not_overridden() -> None:
    source = make_source(category="think_tank")
    job = raw(posting_type="predoc")
    assert detect_posting_type(job, source) == "predoc"


# ── location parsing ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("location", "expected_city", "expected_remote"),
    [
        ("Washington, DC", "dc", False),
        ("New York City, NY", "nyc", False),
        ("San Francisco, CA", "bay_area", False),
        ("London, UK", "london", False),
        ("Paris, France", "paris", False),
        ("Remote", None, True),
    ],
)
def test_parse_location(location: str, expected_city: str | None, expected_remote: bool) -> None:
    result = parse_location(location)
    assert result.get("is_remote") == expected_remote
    if expected_city:
        assert result.get("city") == expected_city


# ── full normalize ────────────────────────────────────────────────────────────────


def test_normalize_sets_description_clean_from_html() -> None:
    source = make_source(name="Brookings")
    job = raw(description_html="<h1>Role</h1><p>Join us as a <strong>Policy Analyst</strong>.</p>")
    result = normalize(job, source)
    assert result["description_clean"] is not None
    assert "Policy Analyst" in result["description_clean"]
    assert "<" not in result["description_clean"]


def test_normalize_company_fallback_to_source_name() -> None:
    source = make_source(name="RAND Corporation")
    job = raw()  # company=None
    result = normalize(job, source)
    assert result["company"] == "RAND Corporation"


def test_normalize_empty_html_gives_none_description_clean() -> None:
    source = make_source()
    job = raw(description_html="  ")
    result = normalize(job, source)
    assert result["description_clean"] is None
