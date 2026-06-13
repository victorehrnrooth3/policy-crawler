"""Tests for the camoufox Tier-2 fetcher — render is stubbed, client is mocked.

No real browser or network is used: ``render_candidates`` is monkeypatched to
return a canned anchors+text blob, and the Anthropic client is a MagicMock that
returns a tool_use payload.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from policy_crawler.crawler import camoufox_llm
from policy_crawler.crawler.camoufox_llm import (
    CamoufoxLLMFetcher,
    _build_blob,
    _Candidates,
    _cost,
    extract_jobs,
)
from tests.crawler.conftest import make_source


def _mock_tool_response(
    tool_input: dict[str, Any], *, input_tokens: int = 1500, output_tokens: int = 200
) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = tool_input

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    msg = MagicMock()
    msg.content = [block]
    msg.usage = usage
    return msg


def _candidates() -> _Candidates:
    return _Candidates(
        anchors=[
            {"text": "Research Analyst", "href": "https://x.org/jobs/123/research-analyst"},
            {"text": "Home", "href": "https://x.org/"},
            {"text": "Senior Fellow", "href": "https://x.org/jobs/456/senior-fellow"},
        ],
        text="Careers at X. Research Analyst — DC. Senior Fellow — London.",
    )


# ── extract_jobs ────────────────────────────────────────────────────────────


def test_extract_jobs_returns_absolute_urls() -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_tool_response(
        {
            "jobs": [
                {
                    "title": "Research Analyst",
                    "url": "/jobs/123/research-analyst",
                    "location": "DC",
                },
                {"title": "Senior Fellow", "url": "https://x.org/jobs/456/senior-fellow"},
            ]
        }
    )

    jobs, in_tok, out_tok = extract_jobs(_candidates(), "https://x.org/careers", "X", client)

    assert [j["title"] for j in jobs] == ["Research Analyst", "Senior Fellow"]
    # Relative URL resolved against careers_url
    assert jobs[0]["url"] == "https://x.org/jobs/123/research-analyst"
    assert jobs[0]["location"] == "DC"
    assert in_tok == 1500
    assert out_tok == 200


def test_extract_jobs_skips_entries_missing_title_or_url() -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_tool_response(
        {
            "jobs": [
                {"title": "", "url": "/x"},
                {"title": "Real", "url": ""},
                {"title": "Keep", "url": "/k"},
            ]
        }
    )
    jobs, _, _ = extract_jobs(_candidates(), "https://x.org", "X", client)
    assert [j["title"] for j in jobs] == ["Keep"]


def test_extract_jobs_empty_candidates_skips_api_call() -> None:
    client = MagicMock()
    jobs, in_tok, out_tok = extract_jobs(_Candidates(), "https://x.org", "X", client)
    assert jobs == []
    assert in_tok == 0
    assert out_tok == 0
    client.messages.create.assert_not_called()


def test_extract_jobs_forces_tool_choice() -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_tool_response({"jobs": []})
    extract_jobs(_candidates(), "https://x.org", "X", client)
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "extract_jobs"}
    assert "haiku" in kwargs["model"].lower()


def test_build_blob_is_truncated() -> None:
    big = _Candidates(anchors=[{"text": "t" * 100, "href": "h" * 100}] * 500, text="z" * 50_000)
    blob = _build_blob(big)
    assert len(blob) <= camoufox_llm._MAX_BLOB_CHARS


def test_cost_positive() -> None:
    assert _cost(1500, 200) > 0


# ── fetch (integration, all I/O mocked) ───────────────────────────────────────


def test_fetch_yields_rawjobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(camoufox_llm, "render_candidates", lambda url, wait: _candidates())
    monkeypatch.setattr(camoufox_llm, "_log_llm_call", lambda *a, **k: None)

    settings = MagicMock()
    settings.anthropic_api_key = "sk-test"
    monkeypatch.setattr(camoufox_llm, "get_settings", lambda: settings)

    client = MagicMock()
    client.messages.create.return_value = _mock_tool_response(
        {"jobs": [{"title": "Research Analyst", "url": "/jobs/1", "location": "DC"}]}
    )
    monkeypatch.setattr(camoufox_llm.anthropic, "Anthropic", lambda **k: client)

    src = make_source(name="X", careers_url="https://x.org/careers", fetcher_kind="camoufox")
    jobs = list(CamoufoxLLMFetcher().fetch(src))

    assert len(jobs) == 1
    assert jobs[0].title == "Research Analyst"
    assert jobs[0].company == "X"
    assert jobs[0].url == "https://x.org/jobs/1"
    assert jobs[0].canonical_id  # sha1 of url


def test_fetch_render_failure_yields_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, wait: int) -> _Candidates:
        raise RuntimeError("camoufox not installed")

    monkeypatch.setattr(camoufox_llm, "render_candidates", boom)
    settings = MagicMock()
    settings.anthropic_api_key = "sk-test"
    monkeypatch.setattr(camoufox_llm, "get_settings", lambda: settings)
    monkeypatch.setattr(camoufox_llm.anthropic, "Anthropic", lambda **k: MagicMock())

    src = make_source(name="X", fetcher_kind="camoufox")
    assert list(CamoufoxLLMFetcher().fetch(src)) == []
