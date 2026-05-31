"""Profile YAML loading and prompt rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_DEFAULT_PATH = Path(__file__).parents[3] / "data" / "profile.yaml"
_TOKEN_BUDGET = 1_500  # max tokens for the profile block in a prompt (~6 000 chars)
_CHARS_PER_TOKEN = 4


class _Topic(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)


class _Exemplar(BaseModel):
    title: str
    company: str
    why: str
    topic: str


class _Exemplars(BaseModel):
    liked: list[_Exemplar] = Field(default_factory=list)
    disliked: list[_Exemplar] = Field(default_factory=list)


class _Identity(BaseModel):
    summary: str
    cv_url: str = ""


class _Geography(BaseModel):
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    acceptable: list[str] = Field(default_factory=list)
    hard_no: list[str] = Field(default_factory=list)
    timeline_note: str = ""


class _Topics(BaseModel):
    heavy: list[_Topic] = Field(default_factory=list)
    medium: list[_Topic] = Field(default_factory=list)
    low: list[_Topic] = Field(default_factory=list)
    negative: list[_Topic] = Field(default_factory=list)


class Profile(BaseModel):
    version: int = 1
    identity: _Identity
    career_thesis: str
    topics: _Topics
    geography: _Geography
    seniority_fit: str = ""
    must_haves: list[str] = Field(default_factory=list)
    dealbreakers: list[str] = Field(default_factory=list)
    soft_negatives: list[str] = Field(default_factory=list)
    posting_type_notes: dict[str, Any] = Field(default_factory=dict)
    exemplars: _Exemplars = Field(default_factory=_Exemplars)


def load_profile(path: Path = _DEFAULT_PATH) -> Profile:
    """Parse and validate profile.yaml."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Profile.model_validate(data)


def profile_for_prompt(profile: Profile) -> str:
    """Render the profile to a markdown string for inclusion in LLM prompts.

    Trimmed to approximately _TOKEN_BUDGET tokens (~6 000 chars).
    """
    parts: list[str] = []

    parts.append(f"## About me\n{profile.identity.summary.strip()}")
    parts.append(f"## Career thesis\n{profile.career_thesis.strip()}")

    # Topics (most important for scoring)
    heavy_names = ", ".join(t.name for t in profile.topics.heavy)
    medium_names = ", ".join(t.name for t in profile.topics.medium)
    negative_names = ", ".join(t.name for t in profile.topics.negative)
    parts.append(
        f"## Topics\n"
        f"**Heavy weight (strong positive):** {heavy_names}\n\n"
        f"**Medium weight:** {medium_names}\n\n"
        f"**Negative (avoid):** {negative_names}"
    )

    geo = profile.geography
    parts.append(
        f"## Geography\n"
        f"Primary: {', '.join(geo.primary)}  \n"
        f"Secondary: {', '.join(geo.secondary)}  \n"
        f"Acceptable: {', '.join(geo.acceptable)}  \n"
        f"Note: {geo.timeline_note}"
    )

    if profile.must_haves:
        items = "\n".join(f"- {m}" for m in profile.must_haves)
        parts.append(f"## Must-haves\n{items}")

    if profile.dealbreakers:
        items = "\n".join(f"- {d}" for d in profile.dealbreakers)
        parts.append(f"## Dealbreakers (score ≤ 30 if any hit)\n{items}")

    if profile.soft_negatives:
        items = "\n".join(f"- {s}" for s in profile.soft_negatives)
        parts.append(f"## Soft negatives\n{items}")

    text = "\n\n".join(parts)

    # Trim to token budget
    max_chars = _TOKEN_BUDGET * _CHARS_PER_TOKEN
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n\n[…profile truncated to token budget…]"

    return text


def format_exemplars(profile: Profile, *, liked_n: int = 3, disliked_n: int = 3) -> str:
    """Render a handful of liked/disliked exemplars as markdown few-shot context."""
    lines: list[str] = ["## Calibration exemplars"]

    liked = profile.exemplars.liked[:liked_n]
    if liked:
        lines.append("**Liked (positive examples):**")
        for ex in liked:
            lines.append(f'- "{ex.title}" at {ex.company}: {ex.why}')

    disliked = profile.exemplars.disliked[:disliked_n]
    if disliked:
        lines.append("**Disliked (negative examples):**")
        for ex in disliked:
            lines.append(f'- "{ex.title}" at {ex.company}: {ex.why}')

    return "\n".join(lines)
