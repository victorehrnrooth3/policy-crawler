"""Status page — last runs, LLM costs, source health. No auth required."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from policy_crawler.db import connection
from policy_crawler.webapp.deps import templates

router = APIRouter()


@router.get("/status", response_class=HTMLResponse)
async def status_page(request: Request) -> HTMLResponse:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, kind, status, started_at, finished_at, "
            "jobs_seen, jobs_new, llm_calls_count, total_cost_usd, error "
            "FROM runs ORDER BY started_at DESC LIMIT 20"
        )
        runs = cur.fetchall()

        cur.execute(
            "SELECT kind, model, SUM(cost_usd) AS total_cost, "
            "SUM(input_tokens) AS total_input, SUM(output_tokens) AS total_output, "
            "COUNT(*) AS calls "
            "FROM llm_calls WHERE created_at >= now() - interval '7 days' "
            "GROUP BY kind, model ORDER BY total_cost DESC"
        )
        llm_stats = cur.fetchall()

        cur.execute(
            "SELECT id, name, enabled, fetcher_kind, last_checked_at, last_success_at "
            "FROM sources ORDER BY name"
        )
        sources = cur.fetchall()

        cur.execute("SELECT COUNT(*) AS total FROM jobs")
        job_count_row = cur.fetchone()
        job_count = job_count_row["total"] if job_count_row else 0

        cur.execute("SELECT COUNT(*) AS total FROM jobs WHERE pass1_score IS NOT NULL")
        scored_row = cur.fetchone()
        scored_count = scored_row["total"] if scored_row else 0

    return templates.TemplateResponse(
        request,
        "status.html",
        {
            "runs": runs,
            "llm_stats": llm_stats,
            "sources": sources,
            "job_count": job_count,
            "scored_count": scored_count,
        },
    )
