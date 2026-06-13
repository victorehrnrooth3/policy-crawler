"""Aggregate the past week's feedback into a compact summary for self-update.

The summary is the only feedback context the Sonnet diff-proposer sees, so it has
to be both small (token budget) and high-signal: vote tallies, the actual liked /
disliked jobs with any free-text the user wrote, the posting-type mix, a light
geography read, and recurring keywords pulled from free-text comments.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import structlog

from policy_crawler.db import connection

logger = structlog.get_logger(__name__)

# up/save read as positive signal; down/hidden as negative. `applied` is strongly
# positive but rare — folded into "liked".
_POSITIVE_VOTES = {"up", "save", "applied"}
_NEGATIVE_VOTES = {"down", "hidden"}

_MAX_LISTED = 12  # cap liked/disliked lists fed to the prompt
_MAX_THEMES = 12

# Geography tokens we care about (mirrors profile.geography + sources.geography_tags).
_GEO_TOKENS = (
    "london",
    "nyc",
    "new york",
    "bay area",
    "san francisco",
    "boston",
    "dc",
    "washington",
    "paris",
    "brussels",
    "geneva",
    "remote",
    "chicago",
)

# Stopwords stripped before counting free-text themes. Deliberately small — we
# only need to suppress the most common filler so real signal words surface.
_STOPWORD_TEXT = (
    "a an the and or but of to in on at for with without is are was were be been being this "
    "that these those it its as by from too very not no yes do does did i me my we our you your "
    "role roles job jobs position seems looks like good bad great nice really just only also more "
    "less than then them they he she his her work working"
)
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())

_SELECT_RECENT_FEEDBACK = """
SELECT f.vote, f.freetext, j.title, j.company, j.location_raw, j.posting_type
FROM feedback f
JOIN jobs j ON j.id = f.job_id
WHERE f.created_at >= now() - make_interval(days => %s)
ORDER BY f.created_at DESC
"""


@dataclass
class FeedbackItem:
    vote: str
    title: str
    company: str
    location: str
    posting_type: str
    freetext: str


@dataclass
class FeedbackSummary:
    window_days: int
    total: int = 0
    by_vote: dict[str, int] = field(default_factory=dict)
    posting_type_counts: dict[str, int] = field(default_factory=dict)
    geography_counts: dict[str, int] = field(default_factory=dict)
    liked: list[FeedbackItem] = field(default_factory=list)
    disliked: list[FeedbackItem] = field(default_factory=list)
    themes: list[tuple[str, int]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    def to_prompt(self) -> str:
        """Render the summary as compact markdown for the diff-proposer prompt."""
        lines: list[str] = [f"## Feedback over the last {self.window_days} days"]
        votes = ", ".join(f"{k}={v}" for k, v in sorted(self.by_vote.items())) or "(none)"
        lines.append(f"**Vote tally:** {votes} (total {self.total})")

        if self.posting_type_counts:
            pt = ", ".join(f"{k}={v}" for k, v in sorted(self.posting_type_counts.items()))
            lines.append(f"**Posting types:** {pt}")
        if self.geography_counts:
            geo = ", ".join(f"{k}={v}" for k, v in sorted(self.geography_counts.items()))
            lines.append(f"**Geography mentions:** {geo}")
        if self.themes:
            themes = ", ".join(f"{w}({n})" for w, n in self.themes)
            lines.append(f"**Recurring free-text themes:** {themes}")

        if self.liked:
            lines.append("\n**Liked (up / save / applied):**")
            lines.extend(_fmt_item(it) for it in self.liked)
        if self.disliked:
            lines.append("\n**Disliked (down / hidden):**")
            lines.extend(_fmt_item(it) for it in self.disliked)

        return "\n".join(lines)


def _fmt_item(it: FeedbackItem) -> str:
    loc = f" [{it.location}]" if it.location else ""
    note = f' — "{it.freetext}"' if it.freetext else ""
    return f"- {it.title} at {it.company}{loc}{note}"


def _count_geography(text: str, counter: Counter[str]) -> None:
    low = text.lower()
    for token in _GEO_TOKENS:
        if token in low:
            counter[token] += 1


def _extract_themes(freetexts: list[str]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for ft in freetexts:
        for word in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", ft.lower()):
            if word not in _STOPWORDS:
                counter[word] += 1
    return [(w, n) for w, n in counter.most_common(_MAX_THEMES) if n >= 2]


def summarize(window_days: int = 7) -> FeedbackSummary:
    """Aggregate feedback rows from the last *window_days* into a FeedbackSummary."""
    summary = FeedbackSummary(window_days=window_days)

    with connection() as conn, conn.cursor() as cur:
        cur.execute(_SELECT_RECENT_FEEDBACK, (window_days,))
        rows = cur.fetchall()

    if not rows:
        logger.info("self_update.summarize.no_feedback", window_days=window_days)
        return summary

    by_vote: Counter[str] = Counter()
    posting_types: Counter[str] = Counter()
    geo: Counter[str] = Counter()
    freetexts: list[str] = []

    for r in rows:
        vote = (r.get("vote") or "").strip()
        item = FeedbackItem(
            vote=vote,
            title=(r.get("title") or "Unknown").strip(),
            company=(r.get("company") or "Unknown").strip(),
            location=(r.get("location_raw") or "").strip(),
            posting_type=(r.get("posting_type") or "unknown").strip(),
            freetext=(r.get("freetext") or "").strip(),
        )
        by_vote[vote] += 1
        posting_types[item.posting_type] += 1
        _count_geography(item.location, geo)
        if item.freetext:
            freetexts.append(item.freetext)
            _count_geography(item.freetext, geo)

        if vote in _POSITIVE_VOTES and len(summary.liked) < _MAX_LISTED:
            summary.liked.append(item)
        elif vote in _NEGATIVE_VOTES and len(summary.disliked) < _MAX_LISTED:
            summary.disliked.append(item)

    summary.total = len(rows)
    summary.by_vote = dict(by_vote)
    summary.posting_type_counts = dict(posting_types)
    summary.geography_counts = dict(geo)
    summary.themes = _extract_themes(freetexts)

    logger.info(
        "self_update.summarize.done",
        window_days=window_days,
        total=summary.total,
        liked=len(summary.liked),
        disliked=len(summary.disliked),
    )
    return summary


def summary_to_jsonable(summary: FeedbackSummary) -> dict[str, Any]:
    """Flatten a FeedbackSummary for storage in the proposed-change audit row."""
    return {
        "window_days": summary.window_days,
        "total": summary.total,
        "by_vote": summary.by_vote,
        "posting_type_counts": summary.posting_type_counts,
        "geography_counts": summary.geography_counts,
        "themes": [list(t) for t in summary.themes],
        "liked": [vars(it) for it in summary.liked],
        "disliked": [vars(it) for it in summary.disliked],
    }
