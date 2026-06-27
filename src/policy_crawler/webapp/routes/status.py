"""Status page — recent runs, LLM costs vs caps, source health, pending queues.

Unauthenticated by design (only counts + timestamps, nothing personal). The
``/status.json`` sibling exposes the same headline numbers for future Slack /
Telegram integrations.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from policy_crawler.config import get_settings
from policy_crawler.db import connection
from policy_crawler.obs.cost import daily_spend, monthly_spend
from policy_crawler.webapp.deps import templates

router = APIRouter()


def _gap_days(last_success_at: datetime | None) -> int | None:
    if last_success_at is None:
        return None
    return (datetime.now(UTC) - last_success_at).days


def _gather() -> dict[str, Any]:
    today = date.today()
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, kind, status, started_at, finished_at, "
            "jobs_seen, jobs_new, llm_calls_count, total_cost_usd, error "
            "FROM runs ORDER BY started_at DESC LIMIT 14"
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
            "SELECT name, category, fetcher_kind, enabled, last_checked_at, last_success_at "
            "FROM sources WHERE enabled ORDER BY last_success_at ASC NULLS FIRST, name"
        )
        sources = [dict(s) for s in cur.fetchall()]

        cur.execute("SELECT COUNT(*) AS n FROM suggested_sources WHERE status = 'pending'")
        row = cur.fetchone()
        pending_sources = row["n"] if row else 0

        cur.execute("SELECT COUNT(*) AS n FROM proposed_profile_changes WHERE status = 'pending'")
        row = cur.fetchone()
        pending_changes = row["n"] if row else 0

        cur.execute("SELECT COUNT(*) AS total FROM jobs")
        row = cur.fetchone()
        job_count = row["total"] if row else 0

        cur.execute("SELECT COUNT(*) AS total FROM jobs WHERE pass1_score IS NOT NULL")
        row = cur.fetchone()
        scored_count = row["total"] if row else 0

    for s in sources:
        s["gap_days"] = _gap_days(s.get("last_success_at"))

    settings = get_settings()
    return {
        "runs": runs,
        "llm_stats": llm_stats,
        "sources": sources,
        "pending_sources": pending_sources,
        "pending_changes": pending_changes,
        "job_count": job_count,
        "scored_count": scored_count,
        "daily_spend": daily_spend(today),
        "daily_cap": settings.daily_soft_cap_usd,
        "monthly_spend": monthly_spend(today),
        "monthly_cap": settings.monthly_soft_cap_usd,
    }


@router.get("/status", response_class=HTMLResponse)
async def status_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "status.html", _gather())


@router.get("/status.json", response_class=JSONResponse)
async def status_json() -> JSONResponse:
    data = _gather()
    last_run = data["runs"][0] if data["runs"] else None
    return JSONResponse(
        {
            "last_run": {
                "kind": last_run["kind"],
                "status": last_run["status"],
                "started_at": last_run["started_at"].isoformat() if last_run else None,
                "total_cost_usd": float(last_run["total_cost_usd"]),
            }
            if last_run
            else None,
            "daily_spend_usd": round(data["daily_spend"], 4),
            "daily_cap_usd": data["daily_cap"],
            "monthly_spend_usd": round(data["monthly_spend"], 4),
            "monthly_cap_usd": data["monthly_cap"],
            "pending_sources": data["pending_sources"],
            "pending_changes": data["pending_changes"],
            "sources_overdue": sum(
                1 for s in data["sources"] if s["gap_days"] is None or s["gap_days"] > 3
            ),
        }
    )
