"""Ranker orchestrator: score_pending() runs both passes and persists results."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from uuid import UUID

import anthropic
import structlog

from policy_crawler.config import get_settings
from policy_crawler.db import connection, get_pool
from policy_crawler.ranker.pass1 import Pass1Result, screen
from policy_crawler.ranker.pass2 import Pass2Result, deep_score
from policy_crawler.ranker.profile import load_profile

logger = structlog.get_logger(__name__)

MAX_PASS1_PER_RUN = 200
MAX_PASS2_PER_RUN = 30

# ── SQL ─────────────────────────────────────────────────────────────────────────

_SELECT_UNSCORED = """
SELECT j.id, j.source_id, j.title, j.company, j.location_raw, j.posting_type,
       j.description_clean, j.description_raw, j.pass1_score, j.pass1_confidence,
       s.priority AS source_priority
FROM jobs j
JOIN sources s ON s.id = j.source_id
WHERE j.pass1_score IS NULL
ORDER BY s.priority DESC, j.first_seen_at DESC
LIMIT %s
"""

_SELECT_PASS2_ELIGIBLE = """
SELECT j.id, j.source_id, j.title, j.company, j.location_raw, j.posting_type,
       j.description_clean, j.description_raw,
       j.pass1_score, j.pass1_confidence,
       s.priority AS source_priority
FROM jobs j
JOIN sources s ON s.id = j.source_id
WHERE j.pass2_score IS NULL
  AND (
      j.pass1_score >= 60
      OR j.pass1_confidence = 'low'
      OR s.priority = 5
  )
ORDER BY coalesce(j.pass1_score, 0) DESC, s.priority DESC
LIMIT %s
"""

_SELECT_RECENT_FEEDBACK = """
SELECT f.vote, j.title, j.company, f.freetext
FROM feedback f
JOIN jobs j ON j.id = f.job_id
ORDER BY f.created_at DESC
LIMIT 10
"""

_UPDATE_PASS1 = """
UPDATE jobs SET
    pass1_score            = %s,
    pass1_reason           = %s,
    pass1_confidence       = %s,
    pass1_dealbreaker_hits = %s
WHERE id = %s
"""

_UPDATE_PASS2 = """
UPDATE jobs SET
    pass2_score               = %s,
    pass2_reason_to_consider  = %s,
    pass2_concerns            = %s,
    pass2_matched_signals     = %s,
    pass2_missing_info        = %s,
    pass2_recommended_action  = %s
WHERE id = %s
"""

_INSERT_LLM_CALL = """
INSERT INTO llm_calls
    (run_id, kind, model, input_tokens, output_tokens, cost_usd, error)
VALUES (%s, %s::llm_call_kind, %s, %s, %s, %s, %s)
"""


# ── Summary ─────────────────────────────────────────────────────────────────────


@dataclass
class RankerSummary:
    pass1_scored: int = 0
    pass2_scored: int = 0
    total_cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


# ── DB writes ────────────────────────────────────────────────────────────────────


def _write_pass1_results(results: list[Pass1Result], run_id: UUID | None) -> None:
    with connection() as conn, conn.cursor() as cur:
        for r in results:
            if r.error and r.fit_score == 0 and not r.screen_reason:
                continue  # skip total failures
            cur.execute(
                _UPDATE_PASS1,
                (
                    r.fit_score,
                    r.screen_reason or None,
                    r.confidence,
                    r.dealbreaker_hits,
                    r.job_id,
                ),
            )
            cur.execute(
                _INSERT_LLM_CALL,
                (
                    run_id,
                    "pass1",
                    r.model,
                    r.input_tokens,
                    r.output_tokens,
                    r.cost_usd,
                    r.error,
                ),
            )


def _write_pass2_results(results: list[Pass2Result], run_id: UUID | None) -> None:
    with connection() as conn, conn.cursor() as cur:
        for r in results:
            if r.error and r.fit_score == 0:
                continue
            cur.execute(
                _UPDATE_PASS2,
                (
                    r.fit_score,
                    r.reason_to_consider or None,
                    r.concerns or None,
                    r.matched_signals,
                    r.missing_info,
                    r.recommended_action,
                    r.job_id,
                ),
            )
            cur.execute(
                _INSERT_LLM_CALL,
                (
                    run_id,
                    "pass2",
                    r.model,
                    r.input_tokens,
                    r.output_tokens,
                    r.cost_usd,
                    r.error,
                ),
            )


# ── Main entry point ─────────────────────────────────────────────────────────────


def score_pending(
    run_id: UUID | None = None,
    limit: int | None = None,
) -> RankerSummary:
    """Run Pass 1 then Pass 2 on all eligible unscored jobs.

    *run_id* ties LLM calls to a crawler run row (optional).
    *limit* caps the number of jobs each pass considers (for testing).
    """
    summary = RankerSummary()

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    profile = load_profile()

    p1_limit = min(limit or MAX_PASS1_PER_RUN, MAX_PASS1_PER_RUN)
    p2_limit = min(limit or MAX_PASS2_PER_RUN, MAX_PASS2_PER_RUN)

    # ── Pass 1 ────────────────────────────────────────────────────────────────────
    with connection() as conn, conn.cursor() as cur:
        cur.execute(_SELECT_UNSCORED, (p1_limit,))
        unscored_jobs = cur.fetchall()

    if unscored_jobs:
        logger.info("ranker.pass1.start", count=len(unscored_jobs))
        p1_results = screen(list(unscored_jobs), profile, client, run_id)
        _write_pass1_results(p1_results, run_id)
        summary.pass1_scored = len([r for r in p1_results if not r.error])
        summary.total_cost_usd += sum(r.cost_usd for r in p1_results)
        logger.info(
            "ranker.pass1.done", scored=summary.pass1_scored, cost=round(summary.total_cost_usd, 6)
        )

    if p1_limit >= MAX_PASS1_PER_RUN and unscored_jobs and len(unscored_jobs) >= p1_limit:
        logger.warning("ranker.pass1.cap_hit", cap=p1_limit)

    # ── Pass 2 ────────────────────────────────────────────────────────────────────
    with connection() as conn, conn.cursor() as cur:
        cur.execute(_SELECT_PASS2_ELIGIBLE, (p2_limit,))
        eligible_jobs = cur.fetchall()
        cur.execute(_SELECT_RECENT_FEEDBACK)
        recent_votes = cur.fetchall()

    if settings.ranker_degrade_to_haiku_only:
        logger.info("ranker.pass2.skipped_cost_kill_switch")
    elif eligible_jobs:
        logger.info("ranker.pass2.start", count=len(eligible_jobs))
        p2_results = deep_score(list(eligible_jobs), profile, client, list(recent_votes), run_id)
        _write_pass2_results(p2_results, run_id)
        summary.pass2_scored = len([r for r in p2_results if not r.error])
        p2_cost = sum(r.cost_usd for r in p2_results)
        summary.total_cost_usd += p2_cost
        logger.info("ranker.pass2.done", scored=summary.pass2_scored, cost=round(p2_cost, 6))

    if p2_limit >= MAX_PASS2_PER_RUN and eligible_jobs and len(eligible_jobs) >= p2_limit:
        logger.warning("ranker.pass2.cap_hit", cap=p2_limit)

    logger.info(
        "ranker.done",
        pass1=summary.pass1_scored,
        pass2=summary.pass2_scored,
        total_cost=round(summary.total_cost_usd, 6),
    )
    return summary


# ── CLI ──────────────────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Score unscored jobs with the Haiku→Sonnet ranker."
    )
    parser.add_argument(
        "--kind",
        default="daily",
        choices=["daily", "weekly_discovery", "weekly_self_update", "manual"],
        help="Run kind (informational only; default: daily)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=f"Max jobs per pass (default: {MAX_PASS1_PER_RUN}/{MAX_PASS2_PER_RUN})",
    )
    args = parser.parse_args()

    summary = score_pending(limit=args.limit)
    print(
        f"Ranker done: pass1={summary.pass1_scored}, "
        f"pass2={summary.pass2_scored}, "
        f"cost=${summary.total_cost_usd:.4f}"
    )
    import contextlib

    with contextlib.suppress(Exception):
        get_pool().close()

    sys.exit(0)


if __name__ == "__main__":
    main()
