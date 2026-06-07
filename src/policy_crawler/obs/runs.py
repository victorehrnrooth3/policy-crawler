"""Shared run-row lifecycle helpers used by all scheduled pipeline jobs."""

from __future__ import annotations

from uuid import UUID

from policy_crawler.db import connection


def start_run(kind: str) -> UUID:
    """Insert a new runs row with status='started' and return its id."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO runs (kind, status) VALUES (%s::run_kind, 'started') RETURNING id",
            (kind,),
        )
        row = cur.fetchone()
        assert row is not None
        return UUID(str(row["id"]))


def finish_run(
    run_id: UUID,
    *,
    status: str,
    jobs_seen: int = 0,
    jobs_new: int = 0,
    llm_calls_count: int = 0,
    total_cost_usd: float = 0.0,
    error: str | None = None,
) -> None:
    """Update the runs row with final status and summary counters."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE runs
            SET status          = %s::run_status,
                finished_at     = now(),
                jobs_seen       = %s,
                jobs_new        = %s,
                llm_calls_count = %s,
                total_cost_usd  = %s,
                error           = %s
            WHERE id = %s
            """,
            (status, jobs_seen, jobs_new, llm_calls_count, total_cost_usd, error, run_id),
        )
