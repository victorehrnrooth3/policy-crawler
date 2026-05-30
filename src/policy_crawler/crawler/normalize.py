"""Normalize a RawJob + SourceRow into a jobs-table-ready dict."""

from __future__ import annotations

import re
from typing import Any

from markdownify import markdownify

from policy_crawler.crawler.base import RawJob, SourceRow

# ── City canonical-name lookup (text match → geography_tag) ────────────────────

_CITY_ALIASES: dict[str, str] = {
    # DC
    "washington": "dc",
    "washington, dc": "dc",
    "washington d.c.": "dc",
    "district of columbia": "dc",
    "arlington": "dc",
    "bethesda": "dc",
    "mclean": "dc",
    # New York
    "new york": "nyc",
    "new york city": "nyc",
    "nyc": "nyc",
    "brooklyn": "nyc",
    "manhattan": "nyc",
    # Bay Area
    "san francisco": "bay_area",
    "sf": "bay_area",
    "palo alto": "bay_area",
    "mountain view": "bay_area",
    "menlo park": "bay_area",
    "sunnyvale": "bay_area",
    "redwood city": "bay_area",
    "san jose": "bay_area",
    "cupertino": "bay_area",
    "campbell": "bay_area",
    "santa clara": "bay_area",
    # Boston
    "boston": "boston",
    "cambridge": "boston",
    "somerville": "boston",
    "watertown": "boston",
    # London
    "london": "london",
    # Paris
    "paris": "paris",
    # Brussels
    "brussels": "brussels",
    "bruxelles": "brussels",
    # Geneva
    "geneva": "geneva",
    "genève": "geneva",
    # Chicago
    "chicago": "chicago",
    # Other US cities (not in canonical tags → global)
    "austin": "global",
    "denver": "global",
    "seattle": "global",
    "los angeles": "global",
    "dallas": "global",
    "houston": "global",
}


def html_to_markdown(html: str) -> str:
    return markdownify(html, heading_style="ATX", strip=["script", "style"]).strip()


def detect_remote_policy(location: str, description: str) -> str:
    text = f"{location} {description}".lower()
    if re.search(r"\bhybrid\b", text):
        return "hybrid"
    if re.search(r"\bfully[\s-]remote\b|\bremote[\s-]first\b|\b100%\s+remote\b", text):
        return "remote"
    if re.search(r"\bremote\b", text):
        return "remote"
    if re.search(r"\bon[\s-]?site\b|\bin[\s-]?office\b|\bin[\s-]?person\b", text):
        return "onsite"
    return "unknown"


def detect_seniority(title: str) -> str:
    t = title.lower()
    if re.search(r"\bintern\b|\binternship\b|\bstudent\b|\bco-?op\b", t):
        return "intern"
    if re.search(r"\bchief\b|\bcto\b|\bcoo\b|\bcfo\b|\bceo\b|\bpresident\b|\bpartner\b", t):
        return "exec"
    if re.search(r"\bdirector\b|\bvp\b|\bvice president\b|\bmanaging\b", t):
        return "lead"
    if re.search(r"\bsenior\b|\bsr\.?\b|\bprincipal\b|\bstaff\b|\blead\b", t):
        return "senior"
    if re.search(r"\bjunior\b|\bjr\.?\b|\bassociate\b|\bentry[\s-]?level\b", t):
        return "early_career"
    if re.search(
        r"\banalyst\b|\bspecialist\b|\bresearcher\b|\bfellow\b|\bscientist\b|\beconomist\b|\badvisor\b",
        t,
    ):
        return "mid"
    return "unknown"


def detect_posting_type(raw: RawJob, source: SourceRow) -> str:
    if raw.posting_type != "unknown":
        return raw.posting_type

    cat = source.get("category", "")
    if cat == "predoc_program":
        return "predoc"
    if cat == "phd_program":
        return "program_call"
    if cat == "fellowship":
        return "fellowship"

    url_lower = raw.url.lower()
    title_lower = raw.title.lower()

    if re.search(r"phd|doctoral|admissions|application", url_lower):
        return "program_call"
    if re.search(r"\bfellow(?:ship)?\b", title_lower):
        return "fellowship"
    if re.search(r"\bpre-?doc\b|\bresearch\s+assistant\b|\bpredoctoral\b", title_lower):
        return "predoc"

    return "role"


def parse_location(location_raw: str) -> dict[str, Any]:
    if not location_raw:
        return {}

    text = location_raw.lower().strip()

    if re.search(r"\bremote\b", text):
        return {"is_remote": True}

    for alias, canonical in _CITY_ALIASES.items():
        if alias in text:
            return {"city": canonical, "is_remote": False}

    return {"city": text[:80], "is_remote": False}


def normalize(raw: RawJob, source: SourceRow) -> dict[str, Any]:
    """Convert a RawJob into a dict ready for the jobs table."""
    desc_html = raw.description_html or ""
    desc_clean = html_to_markdown(desc_html) if desc_html.strip() else None
    location = raw.location_raw or ""

    return {
        "source_id": source["id"],
        "canonical_id": raw.canonical_id,
        "url": raw.url,
        "title": raw.title,
        "company": raw.company or source.get("name"),
        "location_raw": raw.location_raw,
        "location_parsed": parse_location(location),
        "remote_policy": detect_remote_policy(location, desc_clean or ""),
        "seniority": detect_seniority(raw.title),
        "posting_type": detect_posting_type(raw, source),
        "description_raw": raw.description_raw,
        "description_clean": desc_clean,
        "compensation": raw.compensation,
    }
