"""Tests for digest/template.py — rendering HTML and plain-text emails."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from typing import Any
from uuid import uuid4

import pytest

_MOCK_SECRET = "test-secret-key-for-template-tests!!"
_MOCK_BASE_URL = "https://app.example.com"


@pytest.fixture(autouse=True)
def _template_settings(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    from policy_crawler.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("TOKEN_HMAC_SECRET", _MOCK_SECRET)
    monkeypatch.setenv("WEBAPP_BASE_URL", _MOCK_BASE_URL)
    yield
    get_settings.cache_clear()


def _make_job(**kwargs: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "id": uuid4(),
        "title": "Climate Policy Analyst",
        "company": "Future Energy Corp",
        "location_raw": "London, UK",
        "url": "https://example.com/jobs/1",
        "posting_type": "role",
        "pass1_score": 75,
        "pass1_confidence": "med",
        "pass1_dealbreaker_hits": [],
        "pass1_reason": "Strong policy focus.",
        "pass2_score": 82,
        "pass2_reason_to_consider": "Excellent fit with research background.",
        "pass2_concerns": None,
        "pass2_matched_signals": ["energy policy"],
        "pass2_missing_info": [],
        "pass2_recommended_action": "apply_now",
        "_borderline": False,
    }
    defaults.update(kwargs)
    return defaults


def test_subject_format_with_jobs() -> None:
    from policy_crawler.digest.template import render_digest

    today = date(2026, 6, 6)
    _, _, subject = render_digest(today, [_make_job()])
    assert "[1]" in subject
    assert "Jun" in subject


def test_subject_format_zero_jobs() -> None:
    from policy_crawler.digest.template import render_digest

    today = date(2026, 6, 6)
    _, _, subject = render_digest(today, [])
    assert "[0]" in subject


def test_empty_digest_message_in_html_and_text() -> None:
    from policy_crawler.digest.template import render_digest

    html, text, _ = render_digest(date(2026, 6, 6), [])
    assert "no new" in html.lower()
    assert "no new" in text.lower()


def test_job_title_appears_in_both() -> None:
    from policy_crawler.digest.template import render_digest

    job = _make_job(title="Senior Nuclear Policy Director")
    html, text, _ = render_digest(date(2026, 6, 6), [job])
    assert "Senior Nuclear Policy Director" in html
    assert "Senior Nuclear Policy Director" in text


def test_vote_urls_in_html() -> None:
    from policy_crawler.digest.template import render_digest

    html, _, _ = render_digest(date(2026, 6, 6), [_make_job()])
    assert "/v/up/" in html
    assert "/v/down/" in html
    assert "/v/save/" in html


def test_magic_link_in_html() -> None:
    from policy_crawler.digest.template import render_digest

    html, _, _ = render_digest(date(2026, 6, 6), [_make_job()])
    assert "/m/" in html


def test_vote_urls_use_configured_base_url() -> None:
    from policy_crawler.digest.template import render_digest

    html, _, _ = render_digest(date(2026, 6, 6), [_make_job()])
    assert _MOCK_BASE_URL in html


def test_inbox_url_in_footer() -> None:
    from policy_crawler.digest.template import render_digest

    html, text, _ = render_digest(date(2026, 6, 6), [])
    assert f"{_MOCK_BASE_URL}/inbox" in html
    assert f"{_MOCK_BASE_URL}/inbox" in text


def test_borderline_label_shown() -> None:
    from policy_crawler.digest.template import render_digest

    job = _make_job(_borderline=True)
    html, _, _ = render_digest(date(2026, 6, 6), [job])
    assert "borderline" in html.lower()


def test_no_borderline_label_for_top_job() -> None:
    from policy_crawler.digest.template import render_digest

    job = _make_job(_borderline=False)
    html, _, _ = render_digest(date(2026, 6, 6), [job])
    assert "borderline" not in html.lower()


def test_pass2_score_used_when_available() -> None:
    from policy_crawler.digest.template import render_digest

    job = _make_job(pass1_score=60, pass2_score=88)
    html, _, _ = render_digest(date(2026, 6, 6), [job])
    assert "88/100" in html


def test_falls_back_to_pass1_score() -> None:
    from policy_crawler.digest.template import render_digest

    job = _make_job(pass1_score=63, pass2_score=None, pass2_reason_to_consider=None)
    html, _, _ = render_digest(date(2026, 6, 6), [job])
    assert "63/100" in html


def test_pass2_reason_used_when_available() -> None:
    from policy_crawler.digest.template import render_digest

    job = _make_job(
        pass1_reason="Basic match.",
        pass2_reason_to_consider="Deep expertise in nuclear policy.",
    )
    html, _, _ = render_digest(date(2026, 6, 6), [job])
    assert "Deep expertise in nuclear policy." in html
    assert "Basic match." not in html


def test_multiple_jobs_all_titles_in_html() -> None:
    from policy_crawler.digest.template import render_digest

    jobs = [_make_job(title=f"Job Title {i}") for i in range(5)]
    html, _, subject = render_digest(date(2026, 6, 6), jobs)
    assert "[5]" in subject
    for i in range(5):
        assert f"Job Title {i}" in html


def test_html_is_valid_structure() -> None:
    from policy_crawler.digest.template import render_digest

    html, _, _ = render_digest(date(2026, 6, 6), [_make_job()])
    assert html.strip().startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_text_contains_job_url() -> None:
    from policy_crawler.digest.template import render_digest

    job = _make_job(url="https://jobs.example.com/policy-analyst-42")
    _, text, _ = render_digest(date(2026, 6, 6), [job])
    assert "https://jobs.example.com/policy-analyst-42" in text
