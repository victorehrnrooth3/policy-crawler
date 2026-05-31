"""Tests for ranker/pass1.py — Haiku screen with mocked Anthropic client."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from policy_crawler.ranker.pass1 import Pass1Result, _cost, screen
from policy_crawler.ranker.profile import load_profile

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_job(
    *,
    job_id: uuid.UUID | None = None,
    title: str = "Research Analyst",
    company: str = "CGEP",
    location_raw: str = "New York, NY",
    posting_type: str = "role",
    description_clean: str = "Energy policy research at a leading think tank.",
    source_priority: int = 3,
) -> dict[str, Any]:
    return {
        "id": job_id or uuid.uuid4(),
        "source_id": uuid.uuid4(),
        "title": title,
        "company": company,
        "location_raw": location_raw,
        "posting_type": posting_type,
        "description_clean": description_clean,
        "description_raw": description_clean,
        "pass1_score": None,
        "pass1_confidence": None,
        "source_priority": source_priority,
    }


def _mock_tool_response(
    tool_input: dict[str, Any], *, input_tokens: int = 200, output_tokens: int = 80
) -> MagicMock:
    """Build a fake anthropic.types.Message with a single tool_use block."""
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


def _normal_tool_input() -> dict[str, Any]:
    return {
        "fit_score": 75,
        "confidence": "high",
        "posting_type": "role",
        "geography_match": "secondary",
        "dealbreaker_hits": [],
        "screen_reason": "Strong energy policy match; NYC is secondary geography.",
    }


def _dealbreaker_tool_input() -> dict[str, Any]:
    return {
        "fit_score": 10,
        "confidence": "high",
        "posting_type": "role",
        "geography_match": "mismatch",
        "dealbreaker_hits": ["Pure IB / sell-side"],
        "screen_reason": "Investment banking role — hits finance dealbreaker.",
    }


def _low_confidence_tool_input() -> dict[str, Any]:
    return {
        "fit_score": 55,
        "confidence": "low",
        "posting_type": "unknown",
        "geography_match": "unknown",
        "dealbreaker_hits": [],
        "screen_reason": "Unclear from posting; needs deeper review.",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def profile():
    return load_profile()


def test_cost_calculation() -> None:
    # 1M input tokens = $1, 1M output tokens = $5
    cost = _cost(1_000_000, 1_000_000)
    assert abs(cost - 6.0) < 0.001

    cost_small = _cost(200, 80)
    assert cost_small > 0
    assert cost_small < 0.01


def test_screen_normal_job(profile) -> None:
    job = _make_job()
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_normal_tool_input())

    results = screen([job], profile, mock_client)

    assert len(results) == 1
    r = results[0]
    assert isinstance(r, Pass1Result)
    assert r.fit_score == 75
    assert r.confidence == "high"
    assert r.geography_match == "secondary"
    assert r.dealbreaker_hits == []
    assert r.error is None
    assert r.cost_usd > 0
    assert r.input_tokens == 200
    assert r.output_tokens == 80


def test_screen_dealbreaker_job(profile) -> None:
    job = _make_job(
        title="Investment Banking Analyst",
        company="Goldman Sachs",
        description_clean="Join our IB division for sell-side M&A advisory.",
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_dealbreaker_tool_input())

    results = screen([job], profile, mock_client)

    assert len(results) == 1
    r = results[0]
    assert r.fit_score <= 30
    assert len(r.dealbreaker_hits) >= 1
    assert "sell-side" in r.dealbreaker_hits[0].lower() or "IB" in r.dealbreaker_hits[0]


def test_screen_low_confidence_job(profile) -> None:
    job = _make_job(
        title="Programme Officer",
        company="Unknown Organisation",
        description_clean="Managing various policy programmes.",
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_low_confidence_tool_input())

    results = screen([job], profile, mock_client)

    assert len(results) == 1
    assert results[0].confidence == "low"
    assert results[0].fit_score == 55


def test_screen_multiple_jobs(profile) -> None:
    jobs = [_make_job(title=f"Job {i}") for i in range(3)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_normal_tool_input())

    results = screen(jobs, profile, mock_client)

    assert len(results) == 3
    assert mock_client.messages.create.call_count == 3


def test_screen_api_error_returns_error_result(profile) -> None:
    job = _make_job()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API timeout")

    results = screen([job], profile, mock_client)

    # Both attempts fail → error result appended
    assert len(results) == 1
    assert results[0].error is not None
    assert "API timeout" in results[0].error
    assert results[0].fit_score == 0
    assert results[0].cost_usd == 0.0


def test_screen_retries_on_no_tool_use(profile) -> None:
    job = _make_job()

    # First call returns no tool_use block; second call returns valid response
    no_tool_msg = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Here is my assessment..."
    no_tool_msg.content = [text_block]
    no_tool_msg.usage = MagicMock(input_tokens=100, output_tokens=30)

    valid_msg = _mock_tool_response(_normal_tool_input())

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [no_tool_msg, valid_msg]

    results = screen([job], profile, mock_client)

    assert mock_client.messages.create.call_count == 2
    assert len(results) == 1
    assert results[0].fit_score == 75


def test_screen_uses_haiku_model(profile) -> None:
    job = _make_job()
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_normal_tool_input())

    screen([job], profile, mock_client)

    call_kwargs = mock_client.messages.create.call_args
    assert (
        "haiku"
        in call_kwargs.kwargs.get("model", call_kwargs.args[0] if call_kwargs.args else "").lower()
    )


def test_screen_forces_tool_choice(profile) -> None:
    job = _make_job()
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_normal_tool_input())

    screen([job], profile, mock_client)

    call_kwargs = mock_client.messages.create.call_args
    tool_choice = call_kwargs.kwargs.get("tool_choice", {})
    assert tool_choice.get("type") == "tool"
    assert tool_choice.get("name") == "score_pass1"
