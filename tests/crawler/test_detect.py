"""Tests for ATS detection (offline — canned HTML/URL snippets, no network)."""

from __future__ import annotations

import pytest

from policy_crawler.crawler.detect import detect_ats, detect_from_text


@pytest.mark.parametrize(
    ("text", "kind", "slug", "config_key"),
    [
        (
            '<a href="https://boards.greenhouse.io/anthropic">Jobs</a>',
            "greenhouse",
            "anthropic",
            "board",
        ),
        (
            '<iframe src="https://job-boards.greenhouse.io/figma/embed"></iframe>',
            "greenhouse",
            "figma",
            "board",
        ),
        ('<a href="https://jobs.lever.co/palantir">Careers</a>', "lever", "palantir", "company"),
        ('<a href="https://jobs.ashbyhq.com/openai">Open roles</a>', "ashby", "openai", "org"),
        (
            'script src="https://jobs.smartrecruiters.com/Bosch/postings"',
            "smartrecruiters",
            "Bosch",
            "company",
        ),
        ('<a href="https://apply.workable.com/acme/">Apply</a>', "workable", "acme", "subdomain"),
        (
            '<a href="https://careers-brookings.icims.com/jobs/search">Openings</a>',
            "icims",
            "brookings",
            "org",
        ),
        (
            '<a href="https://ats.rippling.com/eurasia-group/jobs">Job Openings</a>',
            "rippling",
            "eurasia-group",
            "org",
        ),
    ],
)
def test_detect_known_platforms(text: str, kind: str, slug: str, config_key: str) -> None:
    det = detect_from_text(text)
    assert det.kind == kind
    assert det.slug == slug
    assert det.config[config_key] == slug
    assert det.detected is True


def test_detect_workday_builds_cxs_endpoint() -> None:
    text = '<a href="https://blackrock.wd1.myworkdayjobs.com/en-US/BlackRock_Professional">Jobs</a>'
    det = detect_from_text(text)
    assert det.kind == "workday_json"
    # tenant is the first label; site is the trailing path segment
    assert "myworkdayjobs.com/wday/cxs/" in det.config["endpoint"]
    assert det.config["endpoint"].endswith("/jobs")


def test_detect_saashr() -> None:
    text = "https://secure7.saashr.com/ta/6213629.careers?CareersSearch=&ein_id=119000450"
    det = detect_from_text(text)
    assert det.kind == "saashr"
    assert det.config["id"] == "6213629"


def test_detect_falls_back_to_generic_html() -> None:
    text = '<html><body><a href="mailto:jobs@cnas.org">Email us</a></body></html>'
    det = detect_from_text(text)
    assert det.kind == "generic_html"
    assert det.detected is False


def test_detect_ats_offline_mode_does_not_fetch() -> None:
    # Passing html= avoids any network call.
    det = detect_ats("https://example.org/careers", html='href="https://jobs.lever.co/acme"')
    assert det.kind == "lever"
    assert det.config["company"] == "acme"
