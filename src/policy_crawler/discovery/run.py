"""Weekly source discovery (Step 09).

Builds a short "what Victor likes" brief from his profile + recent votes, asks
Sonnet for 10–20 candidate employers, classifies each careers URL with
``detect_ats`` (defaulting to ``camoufox`` when no known ATS is found so an
approved source needs **zero** manual config), and queues the survivors in
``suggested_sources`` (status ``pending``) for human approval in ``/sources``.

No source is ever added autonomously — discovery only proposes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import anthropic
import structlog
from anthropic.types import ToolParam

from policy_crawler.config import get_settings
from policy_crawler.crawler.detect import detect_ats
from policy_crawler.db import connection, execute_write, get_pool
from policy_crawler.ranker.profile import load_profile, profile_for_prompt
from policy_crawler.ranker.prompts import format_recent_feedback

logger = structlog.get_logger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2_048
_INPUT_PRICE_PER_1M = 3.00  # USD — Sonnet 4.6 input
_OUTPUT_PRICE_PER_1M = 15.00  # USD — Sonnet 4.6 output

_VALID_CATEGORIES = {
    "think_tank",
    "asset_manager_policy_institute",
    "geopolitical_risk",
    "corporate_policy_tech",
    "corporate_policy_defense",
    "corporate_policy_energy",
    "igo",
    "government",
    "predoc_program",
    "phd_program",
    "fellowship",
}

# ── SQL ───────────────────────────────────────────────────────────────────────

_SELECT_RECENT_FEEDBACK_30D = """
SELECT f.vote, j.title, j.company, f.freetext
FROM feedback f
JOIN jobs j ON j.id = f.job_id
WHERE f.created_at >= now() - interval '30 days'
ORDER BY f.created_at DESC
LIMIT 30
"""

_SELECT_EXISTING_SOURCE_NAMES = "SELECT name FROM sources"
_SELECT_PENDING_SUGGESTIONS = (
    "SELECT name, careers_url FROM suggested_sources WHERE status = 'pending'"
)

_INSERT_SUGGESTION = """
INSERT INTO suggested_sources
    (name, careers_url, category, fetcher_kind, rationale, example_similar_jobs, status)
VALUES (%s, %s, %s::source_category, %s::fetcher_kind, %s, %s, 'pending')
"""

_INSERT_LLM_CALL = """
INSERT INTO llm_calls (run_id, kind, model, input_tokens, output_tokens, cost_usd, error)
VALUES (%s, 'discovery', %s, %s, %s, %s, %s)
"""


SUGGEST_TOOL: ToolParam = {
    "name": "suggest_sources",
    "description": (
        "Propose employers (think tanks, IGOs, governments, policy-focused arms of "
        "companies, asset managers) whose careers pages are likely to post roles the "
        "user would want, based on their profile and recent votes. Propose real "
        "organizations with a real careers URL — do not invent URLs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "description": "10–20 candidate employers, best first.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Organization name."},
                        "careers_url": {
                            "type": "string",
                            "description": "Best-guess careers/jobs page URL (absolute).",
                        },
                        "category": {
                            "type": "string",
                            "enum": sorted(_VALID_CATEGORIES),
                            "description": "Best-fit category for this organization.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "1–2 sentences: why this fits the user's interests.",
                        },
                        "example_similar_jobs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A few role titles this org typically posts.",
                        },
                    },
                    "required": ["name", "careers_url", "category", "rationale"],
                },
            }
        },
        "required": ["candidates"],
    },
}


@dataclass
class DiscoverySummary:
    candidates_proposed: int = 0
    suggestions_inserted: int = 0
    skipped_duplicate: int = 0
    skipped_unreachable: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


def _cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * _INPUT_PRICE_PER_1M
        + output_tokens / 1_000_000 * _OUTPUT_PRICE_PER_1M
    )


def _extract_tool_input(message: anthropic.types.Message) -> dict[str, Any] | None:
    for block in message.content:
        if block.type == "tool_use":
            return block.input  # type: ignore[return-value]
    return None


def _build_prompt(profile_md: str, feedback_md: str, existing_names: list[str]) -> str:
    existing = ", ".join(sorted(existing_names)) or "(none yet)"
    feedback_section = (
        f"\n\n## Recent votes (most recent first)\n{feedback_md}" if feedback_md else ""
    )
    return (
        f"{profile_md}{feedback_section}\n\n"
        f"---\n\n"
        f"## Employers already tracked (do NOT propose these)\n{existing}\n\n"
        f"Propose 10–20 NEW employers (not in the list above) whose careers pages "
        f"likely post roles matching this profile. Favor organizations similar to the "
        f"ones the user has up-voted. Use the `suggest_sources` tool."
    )


def run_discovery(run_id: UUID | None = None) -> DiscoverySummary:
    """Propose new sources and queue them in ``suggested_sources``."""
    summary = DiscoverySummary()

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    profile_md = profile_for_prompt(load_profile())

    with connection() as conn, conn.cursor() as cur:
        cur.execute(_SELECT_RECENT_FEEDBACK_30D)
        recent_votes = cur.fetchall()
        cur.execute(_SELECT_EXISTING_SOURCE_NAMES)
        existing_names = [r["name"] for r in cur.fetchall()]
        cur.execute(_SELECT_PENDING_SUGGESTIONS)
        pending = cur.fetchall()

    # Dedupe sets (lowercased name + url) covering both live sources and pending queue.
    known_names = {n.lower() for n in existing_names}
    known_names |= {p["name"].lower() for p in pending}
    known_urls = {p["careers_url"].rstrip("/").lower() for p in pending}

    feedback_md = format_recent_feedback(list(recent_votes))
    prompt = _build_prompt(profile_md, feedback_md, existing_names)

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            tools=[SUGGEST_TOOL],
            tool_choice={"type": "tool", "name": "suggest_sources"},
        )
    except Exception as exc:  # noqa: BLE001
        summary.errors.append(f"sonnet: {exc}")
        logger.warning("discovery.api_error", error=str(exc))
        _log_llm_call(run_id, 0, 0, str(exc))
        return summary

    usage = response.usage
    summary.cost_usd = _cost(usage.input_tokens, usage.output_tokens)
    _log_llm_call(run_id, usage.input_tokens, usage.output_tokens, None)

    tool_input = _extract_tool_input(response)
    candidates = (tool_input or {}).get("candidates") or []
    summary.candidates_proposed = len(candidates)
    logger.info("discovery.proposed", count=len(candidates), cost=round(summary.cost_usd, 6))

    to_insert: list[tuple[str, str, str, str, str, list[str]]] = []
    for c in candidates:
        name = (c.get("name") or "").strip()
        url = (c.get("careers_url") or "").strip()
        if not name or not url:
            continue
        if name.lower() in known_names or url.rstrip("/").lower() in known_urls:
            summary.skipped_duplicate += 1
            continue

        category = c.get("category")
        if category not in _VALID_CATEGORIES:
            category = "think_tank"

        det = detect_ats(url)
        if det.kind == "unknown":  # hard fetch failure — don't queue a dead URL
            summary.skipped_unreachable += 1
            logger.info("discovery.skip_unreachable", name=name, url=url, evidence=det.evidence)
            continue
        # Known ATS -> its kind; otherwise the camoufox long-tail fetcher.
        fetcher_kind = det.kind if det.detected else "camoufox"

        rationale = (c.get("rationale") or "").strip()
        examples = [str(x) for x in (c.get("example_similar_jobs") or [])]

        to_insert.append((name, url, category, fetcher_kind, rationale, examples))
        known_names.add(name.lower())
        known_urls.add(url.rstrip("/").lower())

    if to_insert:

        def work(conn: Any) -> None:
            with conn.cursor() as cur:
                for row in to_insert:
                    cur.execute(_INSERT_SUGGESTION, row)

        execute_write(work)
        summary.suggestions_inserted = len(to_insert)

    logger.info(
        "discovery.done",
        inserted=summary.suggestions_inserted,
        duplicates=summary.skipped_duplicate,
        unreachable=summary.skipped_unreachable,
    )
    return summary


def _log_llm_call(
    run_id: UUID | None, input_tokens: int, output_tokens: int, error: str | None
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
    except Exception as exc:  # noqa: BLE001 - cost logging must never break discovery
        logger.warning("discovery.llm_call_log_failed", error=str(exc))


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    summary = run_discovery()
    print(
        f"Discovery: proposed={summary.candidates_proposed}, "
        f"inserted={summary.suggestions_inserted}, "
        f"duplicates={summary.skipped_duplicate}, "
        f"unreachable={summary.skipped_unreachable}, "
        f"cost=${summary.cost_usd:.4f}"
    )
    import contextlib

    with contextlib.suppress(Exception):
        get_pool().close()
    sys.exit(0)


if __name__ == "__main__":
    main()
