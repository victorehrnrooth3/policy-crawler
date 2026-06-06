"""Pass 1 ranker — cheap Haiku screen for every unscored job."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import anthropic
import structlog

from policy_crawler.ranker.profile import Profile, format_exemplars, profile_for_prompt
from policy_crawler.ranker.prompts import SYSTEM_PROMPT, pass1_prompt
from policy_crawler.ranker.schemas import PASS1_TOOL

logger = structlog.get_logger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 256
_INPUT_PRICE_PER_1M = 1.00  # USD — Haiku 4.5 input
_OUTPUT_PRICE_PER_1M = 5.00  # USD — Haiku 4.5 output
_MAX_CHARS = 6_000  # abort + truncate if job content exceeds this


@dataclass
class Pass1Result:
    job_id: UUID
    fit_score: int
    confidence: str
    posting_type: str
    geography_match: str
    dealbreaker_hits: list[str]
    screen_reason: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str = _MODEL
    error: str | None = None


def _as_str_list(val: Any) -> list[str]:
    """Normalize tool output that may be a list OR a JSON-encoded string to list[str]."""
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except (ValueError, TypeError):
            pass
    return []


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


def screen(
    jobs: list[dict[str, Any]],
    profile: Profile,
    client: anthropic.Anthropic,
    run_id: UUID | None = None,
) -> list[Pass1Result]:
    """Screen *jobs* with Haiku. Writes results to DB via the caller (run.py)."""
    profile_md = profile_for_prompt(profile)
    exemplars_md = format_exemplars(profile)
    results: list[Pass1Result] = []

    for job in jobs:
        job_id: UUID = job["id"]
        log = logger.bind(job_id=str(job_id), title=job.get("title"))

        # Guard: skip obviously oversized jobs
        total_chars = len(job.get("description_clean") or "") + len(job.get("title") or "")
        if total_chars > _MAX_CHARS:
            log.info("pass1.truncating_large_job", chars=total_chars)

        prompt = pass1_prompt(profile_md, job, exemplars_md)
        response = None
        tool_input = None

        for attempt in range(2):
            system = (
                SYSTEM_PROMPT
                if attempt == 0
                else (
                    SYSTEM_PROMPT
                    + " IMPORTANT: You MUST call the score_pass1 tool. No text responses."
                )
            )
            try:
                response = client.messages.create(
                    model=_MODEL,
                    max_tokens=_MAX_TOKENS,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                    tools=[PASS1_TOOL],
                    tool_choice={"type": "tool", "name": "score_pass1"},
                )
                tool_input = _extract(response)
                if tool_input is not None:
                    break
                log.warning("pass1.no_tool_use", attempt=attempt)
            except Exception as exc:
                log.warning("pass1.api_error", attempt=attempt, error=str(exc))
                if attempt == 1:
                    results.append(
                        Pass1Result(
                            job_id=job_id,
                            fit_score=0,
                            confidence="low",
                            posting_type=job.get("posting_type") or "unknown",
                            geography_match="unknown",
                            dealbreaker_hits=[],
                            screen_reason="",
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
            Pass1Result(
                job_id=job_id,
                fit_score=int(tool_input["fit_score"]),
                confidence=tool_input["confidence"],
                posting_type=tool_input["posting_type"],
                geography_match=tool_input["geography_match"],
                dealbreaker_hits=_as_str_list(tool_input.get("dealbreaker_hits")),
                screen_reason=tool_input.get("screen_reason") or "",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=_cost(usage.input_tokens, usage.output_tokens),
            )
        )
        log.info(
            "pass1.scored",
            score=results[-1].fit_score,
            confidence=results[-1].confidence,
            cost=round(results[-1].cost_usd, 6),
        )

    return results
