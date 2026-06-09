"""ATS detection: infer which job-board platform a careers URL is backed by.

Used to configure sources (turn a bare ``generic_html`` row into a proper
``greenhouse`` / ``lever`` / ``icims`` / ... row with the right slug) and reused
by the weekly source-discovery job (Step 09) to classify candidate employers.

Detection is signature-based: fetch the careers page with a browser-like UA,
follow redirects, then scan the final URL + HTML for known platform markers and
extract the org slug. Pure string/regex work — no LLM, no DB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# A realistic desktop browser UA — many careers sites 403 a bot-identifying UA.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class AtsDetection:
    """Result of detecting the ATS behind a careers URL."""

    kind: str  # fetcher_kind, e.g. "greenhouse"; "generic_html" / "unknown" if none
    config: dict[str, Any] = field(default_factory=dict)
    slug: str | None = None
    evidence: str | None = None  # the matched URL/marker, for human review

    @property
    def detected(self) -> bool:
        return self.kind not in ("generic_html", "unknown")


# ── Signature patterns ────────────────────────────────────────────────────────
# Each entry: fetcher_kind -> (compiled regex with a `slug` group, config-key).
# The regex is searched against both the final (post-redirect) URL and the HTML.

_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Greenhouse: boards.greenhouse.io/<board>, job-boards.greenhouse.io/<board>,
    # boards-api.greenhouse.io/v1/boards/<board>, embed via grnh.se.
    (
        "greenhouse",
        re.compile(
            r"(?:boards|job-boards|boards-api)\.greenhouse\.io"
            r"(?:/v1/boards)?/(?P<slug>[A-Za-z0-9_-]+)",
            re.I,
        ),
        "board",
    ),
    # Lever: jobs.lever.co/<company>, api.lever.co/v0/postings/<company>.
    (
        "lever",
        re.compile(r"(?:jobs|api)\.lever\.co(?:/v0/postings)?/(?P<slug>[A-Za-z0-9_-]+)", re.I),
        "company",
    ),
    # Ashby: jobs.ashbyhq.com/<org>, api.ashbyhq.com/posting-api/job-board/<org>.
    (
        "ashby",
        re.compile(
            r"ashbyhq\.com/(?:posting-api/job-board/)?(?P<slug>[A-Za-z0-9_.-]+)",
            re.I,
        ),
        "org",
    ),
    # SmartRecruiters: jobs.smartrecruiters.com/<company>, careers.smartrecruiters.com/<company>.
    (
        "smartrecruiters",
        re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/(?P<slug>[A-Za-z0-9_-]+)", re.I),
        "company",
    ),
    # Workable: apply.workable.com/<subdomain>, <subdomain>.workable.com.
    (
        "workable",
        re.compile(
            r"(?:apply\.workable\.com/(?P<slug>[A-Za-z0-9_-]+)"
            r"|(?P<slug2>[A-Za-z0-9_-]+)\.workable\.com)",
            re.I,
        ),
        "subdomain",
    ),
    # iCIMS: careers-<org>.icims.com, <org>.icims.com.
    (
        "icims",
        re.compile(r"(?:careers-)?(?P<slug>[A-Za-z0-9_-]+)\.icims\.com", re.I),
        "org",
    ),
    # Rippling: ats.rippling.com/<org>.
    (
        "rippling",
        re.compile(r"ats\.rippling\.com/(?P<slug>[A-Za-z0-9_-]+)", re.I),
        "org",
    ),
]

# Workday handled specially: needs tenant + site (+ datacenter subdomain) to build
# the cxs endpoint. Real external boards look like
# https://<tenant>.<wdNN>.myworkdayjobs.com[/<lang>]/<site>. Only myworkdayjobs.com
# is the public board; myworkday.com is the internal app and is ignored.
_WORKDAY_RE = re.compile(
    r"https?://(?P<host>(?P<tenant>[A-Za-z0-9_-]+)\.(?:[A-Za-z0-9_-]+\.)*myworkdayjobs\.com)"
    r"(?:/[A-Za-z]{2}-[A-Za-z]{2})?"
    r"/(?P<site>[A-Za-z0-9_-]+)",
    re.I,
)

# SaaSHR / UKG Ready: secure<N>.saashr.com/ta/<id>.careers
_SAASHR_RE = re.compile(r"(?P<host>secure\d*\.saashr\.com)/ta/(?P<id>\d+)", re.I)


def _match_workday(text: str) -> AtsDetection | None:
    m = _WORKDAY_RE.search(text)
    if not m:
        return None
    host, tenant, site = m.group("host"), m.group("tenant"), m.group("site")
    endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    return AtsDetection(
        kind="workday_json",
        config={"endpoint": endpoint},
        slug=f"{tenant}/{site}",
        evidence=m.group(0),
    )


def _match_saashr(text: str) -> AtsDetection | None:
    m = _SAASHR_RE.search(text)
    if not m:
        return None
    return AtsDetection(
        kind="saashr",
        config={"host": m.group("host"), "id": m.group("id")},
        slug=m.group("id"),
        evidence=m.group(0),
    )


def detect_from_text(text: str) -> AtsDetection:
    """Detect ATS from a blob of text (final URL + HTML). No network."""
    # Workday and SaaSHR first — more specific URL shapes.
    if (wd := _match_workday(text)) is not None:
        return wd
    if (sh := _match_saashr(text)) is not None:
        return sh

    for kind, pattern, config_key in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        slug = m.groupdict().get("slug") or m.groupdict().get("slug2")
        if not slug:
            continue
        return AtsDetection(
            kind=kind,
            config={config_key: slug},
            slug=slug,
            evidence=m.group(0),
        )

    return AtsDetection(kind="generic_html")


def detect_ats(careers_url: str, *, html: str | None = None) -> AtsDetection:
    """Detect the ATS behind *careers_url*.

    If *html* is given, detection is offline (no fetch). Otherwise the page is
    fetched with a browser-like UA, redirects followed, and both the final URL
    and body are scanned. On a fetch failure, returns ``unknown`` with the error
    as evidence so the caller can distinguish "no ATS" from "couldn't reach it".
    """
    if html is not None:
        return detect_from_text(f"{careers_url}\n{html}")

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=_HEADERS) as client:
            resp = client.get(careers_url)
        text = f"{resp.url}\n{resp.text}"
    except Exception as exc:  # noqa: BLE001 — detection is best-effort
        logger.warning("detect.fetch_error", url=careers_url, error=str(exc))
        return AtsDetection(kind="unknown", evidence=f"fetch_error: {exc}")

    return detect_from_text(text)


# ── CLI report ──────────────────────────────────────────────────────────────


def _report(yaml_path: str) -> None:
    import json
    from pathlib import Path

    from policy_crawler.seed import load_yaml

    seeds = load_yaml(Path(yaml_path))
    rows: list[dict[str, Any]] = []
    print(f"Detecting ATS for {len(seeds)} sources from {yaml_path}...\n")
    for s in seeds:
        det = detect_ats(s.careers_url)
        rows.append(
            {
                "name": s.name,
                "enabled": s.enabled,
                "current_kind": s.fetcher_kind,
                "detected_kind": det.kind,
                "config": det.config,
                "evidence": det.evidence,
            }
        )
        flag = "" if det.kind == s.fetcher_kind else "  <-- CHANGE"
        print(
            f"  [{'x' if s.enabled else ' '}] {s.name[:42]:<42} "
            f"{s.fetcher_kind:<14} -> {det.kind:<14}{flag}"
        )

    # Histogram
    from collections import Counter

    hist = Counter(r["detected_kind"] for r in rows)
    print("\n=== Detected platform histogram ===")
    for kind, n in hist.most_common():
        print(f"  {n:>3}  {kind}")

    out = Path("out/detect_report.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"\nMachine-readable mapping written to {out}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Detect ATS platforms for sources.")
    parser.add_argument("--report", action="store_true", help="Run detection across all sources")
    parser.add_argument("--file", default="data/sources.yaml", help="Sources YAML path")
    parser.add_argument("--url", help="Detect a single careers URL and print the result")
    args = parser.parse_args()

    if args.url:
        det = detect_ats(args.url)
        print(f"kind={det.kind} slug={det.slug} config={det.config} evidence={det.evidence}")
    elif args.report:
        _report(args.file)
    else:
        parser.error("pass --report or --url")


if __name__ == "__main__":
    main()
