"""Tests for ranker/pass2.py — Sonnet deep score with mocked Anthropic client."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from policy_crawler.ranker.pass2 import Pass2Result, _cost, deep_score
from policy_crawler.ranker.profile import load_profile

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_job(
    *,
    job_id: uuid.UUID | None = None,
    title: str = "Policy Analyst",
    company: str = "Brookings",
    location_raw: str = "Washington, DC",
    posting_type: str = "role",
    description_clean: str = (
        "Research on energy policy and AI governance. Requires quantitative skills. "
        "Excellent communication required. DC-based."
    ),
    pass1_score: int = 72,
    pass1_confidence: str = "high",
    source_priority: int = 4,
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
        "pass1_score": pass1_score,
        "pass1_confidence": pass1_confidence,
        "source_priority": source_priority,
    }


def _mock_tool_response(
    tool_input: dict[str, Any],
    *,
    input_tokens: int = 600,
    output_tokens: int = 200,
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


def _strong_fit_tool_input() -> dict[str, Any]:
    return {
        "fit_score": 85,
        "reason_to_consider": (
            "Energy policy + AI governance is exactly the target. DC secondary geography."
        ),
        "concerns": "May require more than 1-2 years experience for senior level.",
        "matched_signals": ["energy policy", "AI governance", "quantitative skills"],
        "missing_info": ["visa sponsorship policy", "team size"],
        "recommended_action": "apply_now",
    }


def _borderline_tool_input() -> dict[str, Any]:
    return {
        "fit_score": 62,
        "reason_to_consider": "Adjacent topic but not directly in heavy-weight set.",
        "concerns": "Mostly development economics; energy angle is secondary.",
        "matched_signals": ["quantitative research"],
        "missing_info": ["sponsorship", "primary topic focus"],
        "recommended_action": "monitor",
    }


def _skip_tool_input() -> dict[str, Any]:
    return {
        "fit_score": 25,
        "reason_to_consider": "",
        "concerns": "Operations role with no research or policy component.",
        "matched_signals": [],
        "missing_info": [],
        "recommended_action": "skip",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def profile():
    return load_profile()


def test_cost_calculation() -> None:
    cost = _cost(1_000_000, 1_000_000)
    assert abs(cost - 18.0) < 0.001  # $3 input + $15 output

    cost_small = _cost(600, 200)
    assert cost_small > 0
    assert cost_small < 0.01


def test_deep_score_strong_fit(profile) -> None:
    job = _make_job()
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_strong_fit_tool_input())

    results = deep_score([job], profile, mock_client)

    assert len(results) == 1
    r = results[0]
    assert isinstance(r, Pass2Result)
    assert r.fit_score == 85
    assert r.recommended_action == "apply_now"
    assert "energy policy" in r.matched_signals
    assert r.error is None
    assert r.cost_usd > 0


def test_deep_score_borderline_job(profile) -> None:
    job = _make_job(pass1_score=62, pass1_confidence="low")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_borderline_tool_input())

    results = deep_score([job], profile, mock_client)

    assert len(results) == 1
    assert results[0].recommended_action == "monitor"
    assert results[0].fit_score == 62


def test_deep_score_skip_action(profile) -> None:
    job = _make_job(
        title="Operations Manager", description_clean="Manage office operations and logistics."
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_skip_tool_input())

    results = deep_score([job], profile, mock_client)

    assert results[0].recommended_action == "skip"
    assert results[0].fit_score <= 30


def test_deep_score_uses_sonnet_model(profile) -> None:
    job = _make_job()
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_strong_fit_tool_input())

    deep_score([job], profile, mock_client)

    call_kwargs = mock_client.messages.create.call_args
    model = call_kwargs.kwargs.get("model", "")
    assert "sonnet" in model.lower()


def test_deep_score_forces_tool_choice(profile) -> None:
    job = _make_job()
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_strong_fit_tool_input())

    deep_score([job], profile, mock_client)

    call_kwargs = mock_client.messages.create.call_args
    tool_choice = call_kwargs.kwargs.get("tool_choice", {})
    assert tool_choice.get("type") == "tool"
    assert tool_choice.get("name") == "score_pass2"


def test_deep_score_includes_recent_feedback(profile) -> None:
    job = _make_job()
    recent_votes = [
        {"vote": "up", "title": "Energy Analyst", "company": "RFF", "freetext": "Great fit"},
        {"vote": "down", "title": "IB Analyst", "company": "GS", "freetext": None},
    ]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_tool_response(_strong_fit_tool_input())

    deep_score([job], profile, mock_client, recent_votes=recent_votes)

    call_kwargs = mock_client.messages.create.call_args
    messages = call_kwargs.kwargs.get("messages", [])
    user_content = messages[0]["content"] if messages else ""
    # Recent feedback should be embedded in the prompt
    assert "UP" in user_content or "RFF" in user_content


def test_deep_score_api_error_returns_error_result(profile) -> None:
    job = _make_job()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Rate limit exceeded")

    results = deep_score([job], profile, mock_client)

    assert len(results) == 1
    assert results[0].error is not None
    assert "Rate limit" in results[0].error
    assert results[0].fit_score == 0
    assert results[0].recommended_action == "needs_human_review"


def test_deep_score_retries_on_no_tool_use(profile) -> None:
    job = _make_job()

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Let me analyze this..."
    no_tool_msg = MagicMock()
    no_tool_msg.content = [text_block]
    no_tool_msg.usage = MagicMock(input_tokens=400, output_tokens=100)

    valid_msg = _mock_tool_response(_strong_fit_tool_input())

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [no_tool_msg, valid_msg]

    results = deep_score([job], profile, mock_client)

    assert mock_client.messages.create.call_count == 2
    assert len(results) == 1
    assert results[0].fit_score == 85


def test_deep_score_empty_jobs_returns_empty(profile) -> None:
    mock_client = MagicMock()
    results = deep_score([], profile, mock_client)
    assert results == []
    mock_client.messages.create.assert_not_called()
