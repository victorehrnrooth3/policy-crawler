"""Prompt builders for Pass 1 and Pass 2 ranker calls."""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = (
    "You are a calibrated, skeptical evaluator scoring job postings against a user's "
    "preference profile. Be concise. Use the tool to return your judgment — never reply "
    "in free-form text. If a dealbreaker hits, the score MUST be ≤ 30."
)

_MAX_DESC_PASS1 = 1_500  # chars
_MAX_DESC_PASS2 = 4_000  # chars


def _fmt_job(job: dict[str, Any], max_desc_chars: int) -> str:
    title = job.get("title") or "Unknown Title"
    company = job.get("company") or "Unknown Company"
    location = job.get("location_raw") or "Location not specified"
    posting_type = job.get("posting_type") or "unknown"
    desc = job.get("description_clean") or job.get("description_raw") or ""
    desc_excerpt = desc[:max_desc_chars]
    if len(desc) > max_desc_chars:
        desc_excerpt += "\n[…description truncated…]"

    return (
        f"**Title:** {title}\n"
        f"**Company:** {company}\n"
        f"**Location:** {location}\n"
        f"**Posting type (set by system, respect unless obviously wrong):** {posting_type}\n\n"
        f"**Description:**\n{desc_excerpt}"
    )


def pass1_prompt(
    profile_md: str,
    job: dict[str, Any],
    exemplars_md: str,
) -> str:
    """Build the Pass 1 (Haiku screen) user message."""
    job_block = _fmt_job(job, _MAX_DESC_PASS1)
    return (
        f"{profile_md}\n\n"
        f"{exemplars_md}\n\n"
        f"---\n\n"
        f"## Job to score\n\n"
        f"{job_block}\n\n"
        f"Use the `score_pass1` tool to return your assessment."
    )


def pass2_prompt(
    profile_md: str,
    job: dict[str, Any],
    exemplars_md: str,
    recent_feedback_md: str,
) -> str:
    """Build the Pass 2 (Sonnet deep score) user message."""
    job_block = _fmt_job(job, _MAX_DESC_PASS2)
    feedback_section = (
        f"\n\n## Recent feedback context\n{recent_feedback_md}" if recent_feedback_md else ""
    )
    return (
        f"{profile_md}\n\n"
        f"{exemplars_md}"
        f"{feedback_section}\n\n"
        f"---\n\n"
        f"## Job to deep-score\n\n"
        f"{job_block}\n\n"
        f"Use the `score_pass2` tool to return your detailed assessment."
    )


def format_recent_feedback(votes: list[dict[str, Any]], *, max_entries: int = 10) -> str:
    """Render recent vote feedback as a concise bullet list."""
    if not votes:
        return ""
    lines: list[str] = []
    for v in votes[:max_entries]:
        kind = (v.get("vote") or "?").upper()
        title = v.get("title") or "?"
        company = v.get("company") or "?"
        freetext = v.get("freetext") or ""
        note = f" — '{freetext}'" if freetext else ""
        lines.append(f"[{kind}] {title} at {company}{note}")
    return "\n".join(lines)
