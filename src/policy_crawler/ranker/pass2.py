"""Pass 2 ranker — Sonnet deep score for borderline and high-priority jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import anthropic
import structlog

from policy_crawler.ranker.profile import Profile, format_exemplars, profile_for_prompt
from policy_crawler.ranker.prompts import SYSTEM_PROMPT, format_recent_feedback, pass2_prompt
from policy_crawler.ranker.schemas import PASS2_TOOL

logger = structlog.get_logger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 512
_INPUT_PRICE_PER_1M = 3.00  # USD — Sonnet 4.6 input
_OUTPUT_PRICE_PER_1M = 15.00  # USD — Sonnet 4.6 output


@dataclass
class Pass2Result:
    job_id: UUID
    fit_score: int
    reason_to_consider: str
    concerns: str
    matched_signals: list[str]
    missing_info: list[str]
    recommended_action: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str = _MODEL
    error: str | None = None


def _cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * _INPUT_PRICE_PER_1M
        + output_tokens / 1_000_000 * _OUTPUT_PRICE_PER_1M
    )


def _extract(message: anthropic.types.Message) -> dict[str, Any] | None:
    for block in message.content:
        if block.type == "tool_use":
            return block.input  # type: ignore[return-value]
    return None


def deep_score(
    jobs: list[dict[str, Any]],
    profile: Profile,
    client: anthropic.Anthropic,
    recent_votes: list[dict[str, Any]] | None = None,
    run_id: UUID | None = None,
) -> list[Pass2Result]:
    """Deep-score *jobs* with Sonnet. Only eligible jobs should be passed in."""
    profile_md = profile_for_prompt(profile)
    exemplars_md = format_exemplars(profile)
    feedback_md = format_recent_feedback(recent_votes or [])
    results: list[Pass2Result] = []

    for job in jobs:
        job_id: UUID = job["id"]
        log = logger.bind(job_id=str(job_id), title=job.get("title"))

        prompt = pass2_prompt(profile_md, job, exemplars_md, feedback_md)
        response = None
        tool_input = None

        for attempt in range(2):
            system = (
                SYSTEM_PROMPT
                if attempt == 0
                else (
                    SYSTEM_PROMPT
                    + " IMPORTANT: You MUST call the score_pass2 tool. No text responses."
                )
            )
            try:
                response = client.messages.create(
                    model=_MODEL,
                    max_tokens=_MAX_TOKENS,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                    tools=[PASS2_TOOL],
                    tool_choice={"type": "tool", "name": "score_pass2"},
                )
                tool_input = _extract(response)
                if tool_input is not None:
                    break
                log.warning("pass2.no_tool_use", attempt=attempt)
            except Exception as exc:
                log.warning("pass2.api_error", attempt=attempt, error=str(exc))
                if attempt == 1:
                    results.append(
                        Pass2Result(
                            job_id=job_id,
                            fit_score=0,
                            reason_to_consider="",
                            concerns="",
                            matched_signals=[],
                            missing_info=[],
                            recommended_action="needs_human_review",
                            input_tokens=0,
                            output_tokens=0,
                            cost_usd=0.0,
                            error=str(exc),
                        )
                    )

        if tool_input is None or response is None:
            continue

        usage = response.usage
        results.append(
            Pass2Result(
                job_id=job_id,
                fit_score=int(tool_input["fit_score"]),
                reason_to_consider=tool_input.get("reason_to_consider") or "",
                concerns=tool_input.get("concerns") or "",
                matched_signals=tool_input.get("matched_signals") or [],
                missing_info=tool_input.get("missing_info") or [],
                recommended_action=tool_input.get("recommended_action") or "needs_human_review",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=_cost(usage.input_tokens, usage.output_tokens),
            )
        )
        log.info(
            "pass2.scored",
            score=results[-1].fit_score,
            action=results[-1].recommended_action,
            cost=round(results[-1].cost_usd, 6),
        )

    return results
