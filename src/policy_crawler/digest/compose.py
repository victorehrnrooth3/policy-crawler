"""Pick jobs for the daily digest and mark them as sent."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import structlog

from policy_crawler.config import get_settings
from policy_crawler.db import connection

logger = structlog.get_logger(__name__)

# Jobs are eligible if unsent, scored, still open, not deleted, and free of
# dealbreaker hits. program_call postings may have soft mismatches that shouldn't
# block them.
_SELECT_DIGEST_ELIGIBLE = """
SELECT j.id, j.title, j.company, j.location_raw, j.url, j.posting_type,
       j.pass1_score, j.pass1_confidence, j.pass1_dealbreaker_hits, j.pass1_reason,
       j.pass2_score, j.pass2_reason_to_consider, j.pass2_concerns,
       j.pass2_matched_signals, j.pass2_missing_info, j.pass2_recommended_action
FROM jobs j
WHERE j.digest_sent_at IS NULL
  AND j.pass1_score IS NOT NULL
  AND j.closed_at IS NULL
  AND j.deleted_at IS NULL
  AND (
      coalesce(cardinality(j.pass1_dealbreaker_hits), 0) = 0
      OR j.posting_type = 'program_call'
  )
ORDER BY coalesce(j.pass2_score, j.pass1_score) DESC NULLS LAST
"""

_UPDATE_DIGEST_SENT = """
UPDATE jobs SET digest_sent_at = now() WHERE id = ANY(%s)
"""


def _effective_score(row: dict[str, Any]) -> int:
    score = row.get("pass2_score")
    if score is None:
        score = row.get("pass1_score")
    return int(score) if score is not None else 0


def pick_jobs(
    today: date,
    threshold: int | None = None,
    min_jobs: int | None = None,
    k_borderline: int = 2,
) -> list[dict[str, Any]]:
    """Return all jobs scoring at/above *threshold*, with a floor of *min_jobs*.

    Every eligible job whose effective score (pass2 else pass1) is >= *threshold*
    is included — the list can run well past *min_jobs* on a strong week. If fewer
    than *min_jobs* clear the bar, fall back to the top *min_jobs* by score so the
    digest is never near-empty. Up to *k_borderline* low-confidence outliers are
    appended (unchanged behavior). Defaults come from settings.

    *today* is reserved for future date-based filtering (e.g., deadline awareness
    for fellowships); currently unused in the WHERE clause.
    """
    _ = today  # suppress unused-variable lint; used by callers for logging context
    settings = get_settings()
    if threshold is None:
        threshold = settings.recommended_score_threshold
    if min_jobs is None:
        min_jobs = settings.digest_min_jobs

    with connection() as conn, conn.cursor() as cur:
        cur.execute(_SELECT_DIGEST_ELIGIBLE)
        rows: list[dict[str, Any]] = list(cur.fetchall())  # already score-sorted DESC

    above = [r for r in rows if _effective_score(r) >= threshold]
    top_rows = above if len(above) >= min_jobs else rows[:min_jobs]

    top = [{**r, "_borderline": False} for r in top_rows]
    seen_ids: set[UUID] = {r["id"] for r in top_rows}

    borderline: list[dict[str, Any]] = []
    for row in rows:
        if len(borderline) >= k_borderline:
            break
        if row["id"] in seen_ids:
            continue
        if (
            row.get("pass1_confidence") == "low"
            and row.get("pass1_score") is not None
            and 40 <= row["pass1_score"] <= 60
        ):
            borderline.append({**row, "_borderline": True})

    result = top + borderline
    logger.info(
        "digest.compose.picked",
        top=len(top),
        borderline=len(borderline),
        threshold=threshold,
        above_threshold=len(above),
    )
    return result


def mark_digest_sent(job_ids: list[UUID]) -> None:
    """Bulk-update digest_sent_at = now() for the given job IDs."""
    if not job_ids:
        return
    with connection() as conn, conn.cursor() as cur:
        cur.execute(_UPDATE_DIGEST_SENT, (job_ids,))
    logger.info("digest.compose.marked_sent", count=len(job_ids))
