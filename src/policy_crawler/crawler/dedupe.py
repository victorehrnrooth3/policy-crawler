"""Cross-source deduplication of normalized job dicts."""

from __future__ import annotations

import hashlib
import re
from typing import Any

_STOP_WORDS = re.compile(
    r"\b(inc|llc|ltd|corp|co|company|group|institute|center|centre"
    r"|foundation|trust|association|international|global)\b",
    re.IGNORECASE,
)
_NON_ALPHA = re.compile(r"[^\w\s]")
_SENIORITY_WORDS = re.compile(
    r"\b(senior|junior|sr|jr|lead|principal|staff|associate|entry[\s-]?level|mid[\s-]?level)\b",
    re.IGNORECASE,
)


def _norm_company(name: str) -> str:
    name = _STOP_WORDS.sub("", name.lower())
    return _NON_ALPHA.sub("", name).strip()


def _norm_title(title: str) -> str:
    title = _SENIORITY_WORDS.sub("", title.lower())
    title = _NON_ALPHA.sub("", title)
    return " ".join(title.split())


def dedup_key(job: dict[str, Any]) -> str:
    company = _norm_company(job.get("company") or "")
    title = _norm_title(job.get("title") or "")
    city = (job.get("location_parsed") or {}).get("city", "")
    return hashlib.sha1(f"{company}|{title}|{city}".encode()).hexdigest()


def dedupe(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove cross-source duplicates, keeping the first occurrence."""
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for job in jobs:
        key = dedup_key(job)
        if key in seen:
            continue
        seen.add(key)
        result.append(job)
    return result
