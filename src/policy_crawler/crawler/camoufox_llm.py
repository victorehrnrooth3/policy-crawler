"""Tier-2 fetcher: render any career page with Camoufox, extract roles with Haiku.

This is the single long-tail strategy that replaces the dead
generic_html/playwright/sitemap/rss fetchers. It works on JS-heavy pages and
WAF-gated sites (e.g. iCIMS) that a plain httpx GET cannot read.

Pipeline per source:

1. **Render** the careers URL with Camoufox (Firefox; a different TLS
   fingerprint than headless Chromium, which is what gets past the AWS WAF on
   iCIMS). After load we walk *every* frame and pull the anchor list
   (text + href) plus a slice of ``body.innerText``. Iterating frames is what
   transparently handles iCIMS, whose jobs live inside ``#icims_content_iframe``.
2. **Extract** with a cheap forced Haiku tool call: feed the compact
   anchors+text blob and get back ``[{title, url, location}]``.
3. Yield one :class:`RawJob` per extracted posting (relative URLs resolved,
   ``canonical_id = sha1(url)``), and log a single ``llm_calls`` row for cost.

The browser render is isolated in :func:`render_candidates` so unit tests can
stub it without a real browser.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import anthropic
import structlog
from anthropic.types import ToolParam

from policy_crawler.config import get_settings
from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, absolute_url
from policy_crawler.db import execute_write

logger = structlog.get_logger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 2_048
_INPUT_PRICE_PER_1M = 1.00  # USD — Haiku 4.5 input
_OUTPUT_PRICE_PER_1M = 5.00  # USD — Haiku 4.5 output

_DEFAULT_WAIT_SECONDS = 6
_MAX_BLOB_CHARS = 8_000  # cap the candidate blob fed to Haiku
_MAX_ANCHORS = 400  # cap anchors collected per page
_MAX_INNERTEXT_CHARS = 3_000

# JS run inside each frame: collect anchors (text+href) so we can correlate them
# with job titles. Kept tiny and dependency-free so it runs in any frame. The
# __N__ sentinels are substituted below (the JS uses {} braces, so str.format /
# f-strings are awkward here).
_COLLECT_JS = """
() => {
    const out = [];
    const anchors = document.querySelectorAll('a[href]');
    for (let i = 0; i < anchors.length && out.length < __MAX_ANCHORS__; i++) {
        const a = anchors[i];
        const text = (a.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!text) continue;
        out.push({text: text, href: a.href});
    }
    const body = document.body ? (document.body.innerText || '') : '';
    return {anchors: out, text: body.slice(0, __MAX_INNERTEXT__)};
}
""".replace("__MAX_ANCHORS__", str(_MAX_ANCHORS)).replace(
    "__MAX_INNERTEXT__", str(_MAX_INNERTEXT_CHARS)
)


EXTRACT_TOOL: ToolParam = {
    "name": "extract_jobs",
    "description": (
        "Extract the individual job/role postings from a careers-page snapshot. "
        "Return only real, currently-open positions — ignore navigation links, "
        "category filters, login/apply-generic links, and pagination controls."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "jobs": {
                "type": "array",
                "description": "One entry per distinct job posting found. Empty if none.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "The role title."},
                        "url": {
                            "type": "string",
                            "description": (
                                "Absolute URL to the posting. Use the matching anchor href "
                                "verbatim; do not invent or normalize it."
                            ),
                        },
                        "location": {
                            "type": "string",
                            "description": "Location if shown, else empty string.",
                        },
                    },
                    "required": ["title", "url"],
                },
            }
        },
        "required": ["jobs"],
    },
}


@dataclass
class _Candidates:
    """What a page render yields for the extractor: anchors + visible text."""

    anchors: list[dict[str, str]] = field(default_factory=list)
    text: str = ""


# ── Render (isolated for testability) ─────────────────────────────────────────


def render_candidates(careers_url: str, wait_seconds: int = _DEFAULT_WAIT_SECONDS) -> _Candidates:
    """Load *careers_url* in Camoufox and return anchors + visible text.

    Walks every frame so iframe-hosted boards (iCIMS) are covered. Raises
    ``RuntimeError`` if Camoufox / its browser binary is not installed.
    """
    try:
        from camoufox.sync_api import Camoufox  # lazy: browser toolchain is optional
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "camoufox not installed; run: pip install -e '.[camoufox]' && python -m camoufox fetch"
        ) from exc

    anchors: list[dict[str, str]] = []
    seen_hrefs: set[str] = set()
    texts: list[str] = []

    with Camoufox(headless=True) as browser:
        page = browser.new_page()
        page.goto(careers_url, wait_until="domcontentloaded", timeout=45_000)
        time.sleep(wait_seconds)  # let client-side boards hydrate (and iframes attach)

        for frame in page.frames:
            try:
                result = frame.evaluate(_COLLECT_JS)
            except Exception:  # noqa: BLE001 - a frame may be cross-origin / detached
                continue
            for a in result.get("anchors", []):
                href = a.get("href") or ""
                if href and href not in seen_hrefs:
                    seen_hrefs.add(href)
                    anchors.append({"text": a.get("text") or "", "href": href})
            frame_text = result.get("text") or ""
            if frame_text:
                texts.append(frame_text)

    return _Candidates(anchors=anchors[:_MAX_ANCHORS], text="\n".join(texts))


# ── Extraction ────────────────────────────────────────────────────────────────


def _cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * _INPUT_PRICE_PER_1M
        + output_tokens / 1_000_000 * _OUTPUT_PRICE_PER_1M
    )


def _build_blob(cand: _Candidates) -> str:
    """Compact the render into a token-bounded prompt blob."""
    anchor_lines = [f"- {a['text']}  ->  {a['href']}" for a in cand.anchors if a["text"]]
    blob = (
        "## Page text (truncated)\n"
        f"{cand.text}\n\n"
        "## Links on page (anchor text -> href)\n" + "\n".join(anchor_lines)
    )
    return blob[:_MAX_BLOB_CHARS]


def _extract_tool_input(message: anthropic.types.Message) -> dict[str, Any] | None:
    for block in message.content:
        if block.type == "tool_use":
            return block.input  # type: ignore[return-value]
    return None


def extract_jobs(
    cand: _Candidates,
    careers_url: str,
    source_name: str,
    client: anthropic.Anthropic,
) -> tuple[list[dict[str, str]], int, int]:
    """Ask Haiku to pull job postings from the rendered candidates.

    Returns ``(jobs, input_tokens, output_tokens)`` where each job is
    ``{"title", "url", "location"}`` with an absolute URL.
    """
    if not cand.anchors and not cand.text.strip():
        return [], 0, 0

    blob = _build_blob(cand)
    prompt = (
        f"Below is a snapshot of the careers page for **{source_name}** "
        f"({careers_url}).\n\n{blob}\n\n"
        "Use the `extract_jobs` tool to list every real job posting. "
        "Pick the URL from the matching anchor href verbatim."
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_jobs"},
    )
    tool_input = _extract_tool_input(response)
    usage = response.usage

    jobs: list[dict[str, str]] = []
    if tool_input:
        for j in tool_input.get("jobs") or []:
            title = (j.get("title") or "").strip()
            url = (j.get("url") or "").strip()
            if not title or not url:
                continue
            jobs.append(
                {
                    "title": title,
                    "url": absolute_url(url, careers_url),
                    "location": (j.get("location") or "").strip(),
                }
            )
    return jobs, usage.input_tokens, usage.output_tokens


# ── Fetcher ───────────────────────────────────────────────────────────────────

_INSERT_LLM_CALL = """
INSERT INTO llm_calls (run_id, kind, model, input_tokens, output_tokens, cost_usd, error)
VALUES (%s, 'crawl_extract', %s, %s, %s, %s, %s)
"""


def _log_llm_call(
    run_id: UUID | None,
    input_tokens: int,
    output_tokens: int,
    error: str | None,
) -> None:
    def work(conn: Any) -> None:
        with conn.cursor() as cur:
            cur.execute(
                _INSERT_LLM_CALL,
                (
                    run_id,
                    _MODEL,
                    input_tokens,
                    output_tokens,
                    _cost(input_tokens, output_tokens),
                    error,
                ),
            )

    try:
        execute_write(work)
    except Exception as exc:  # noqa: BLE001 - cost logging must never break a crawl
        logger.warning("camoufox.llm_call_log_failed", error=str(exc))


class CamoufoxLLMFetcher(Fetcher):
    """Render a careers page with Camoufox, extract postings with Haiku."""

    kind = "camoufox"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        name = source["name"]
        careers_url = source["careers_url"]
        config = source.get("fetcher_config") or {}
        wait_seconds = int(config.get("wait_seconds") or _DEFAULT_WAIT_SECONDS)
        run_id = source.get("_run_id")  # injected by crawl_all; None when standalone
        log = logger.bind(source=name)

        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        try:
            cand = render_candidates(careers_url, wait_seconds)
        except Exception as exc:  # noqa: BLE001 - one bad source shouldn't kill the run
            log.warning("camoufox.render_failed", error=str(exc))
            return

        try:
            jobs, in_tok, out_tok = extract_jobs(cand, careers_url, name, client)
        except Exception as exc:  # noqa: BLE001
            log.warning("camoufox.extract_failed", error=str(exc))
            _log_llm_call(run_id, 0, 0, str(exc))
            return

        _log_llm_call(run_id, in_tok, out_tok, None)
        log.info(
            "camoufox.extracted",
            jobs=len(jobs),
            anchors=len(cand.anchors),
            cost=round(_cost(in_tok, out_tok), 6),
        )

        now = datetime.now(UTC)
        for j in jobs:
            url = j["url"]
            if not url:
                continue
            yield RawJob(
                canonical_id=hashlib.sha1(url.encode()).hexdigest(),
                url=url,
                title=j["title"],
                company=name,
                location_raw=j.get("location") or None,
                seen_at=now,
            )
