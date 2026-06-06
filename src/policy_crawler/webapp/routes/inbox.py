"""Inbox routes — list and detail views for digested jobs."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import psycopg.sql as pgsql
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from policy_crawler.db import connection
from policy_crawler.webapp.auth import (
    get_csrf_token,
    require_session,
    set_csrf_cookie,
    verify_csrf,
)
from policy_crawler.webapp.deps import templates

router = APIRouter()

_INBOX_BASE = pgsql.SQL("""
SELECT
    j.id, j.title, j.company, j.location_raw, j.url, j.posting_type,
    j.pass1_score, j.pass1_confidence, j.pass2_score,
    j.pass2_reason_to_consider, j.pass2_concerns, j.pass2_recommended_action,
    j.digest_sent_at, j.first_seen_at,
    s.name  AS source_name,
    s.category AS source_category
FROM jobs j
JOIN sources s ON j.source_id = s.id
WHERE j.digest_sent_at IS NOT NULL
  AND j.digest_sent_at >= now() - interval '14 days'
  {where_extra}
ORDER BY COALESCE(j.pass2_score, j.pass1_score) DESC NULLS LAST
LIMIT 200
""")

_DETAIL_SQL = pgsql.SQL("""
SELECT
    j.*,
    s.name AS source_name, s.careers_url AS source_url, s.category AS source_category
FROM jobs j
JOIN sources s ON j.source_id = s.id
WHERE j.id = %s
""")


@router.get("/inbox", response_class=HTMLResponse)
async def inbox_list(
    request: Request,
    posting_type: str = "",
    min_score: int = 0,
    feedback_state: str = "",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    extra_clauses: list[pgsql.Composed | pgsql.SQL] = []
    params: list[Any] = []

    if posting_type:
        extra_clauses.append(
            pgsql.SQL("AND j.posting_type = {}").format(pgsql.Literal(posting_type))
        )
    if min_score:
        # min_score is cast to int by FastAPI, so safe to embed directly
        extra_clauses.append(
            pgsql.SQL("AND COALESCE(j.pass2_score, j.pass1_score) >= {}").format(
                pgsql.Literal(min_score)
            )
        )

    where_extra = pgsql.SQL(" ").join(extra_clauses) if extra_clauses else pgsql.SQL("")
    sql = _INBOX_BASE.format(where_extra=where_extra)

    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params or None)
        jobs = cur.fetchall()

    # Attach feedback state per job when filtering requested
    if feedback_state and jobs:
        job_ids = [str(j["id"]) for j in jobs]
        with connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ON (job_id) job_id, vote FROM feedback "
                "WHERE job_id = ANY(%s::uuid[]) ORDER BY job_id, created_at DESC",
                (job_ids,),
            )
            votes_by_job = {str(row["job_id"]): row["vote"] for row in cur.fetchall()}

        if feedback_state == "unrated":
            jobs = [j for j in jobs if str(j["id"]) not in votes_by_job]
        else:
            jobs = [j for j in jobs if votes_by_job.get(str(j["id"])) == feedback_state]

    csrf = get_csrf_token(request)
    resp = templates.TemplateResponse(
        request,
        "inbox/list.html",
        {
            "jobs": jobs,
            "posting_type": posting_type,
            "min_score": min_score,
            "feedback_state": feedback_state,
            "csrf_token": csrf,
        },
    )
    set_csrf_cookie(resp, csrf)
    return resp


@router.get("/inbox/{job_id}", response_class=HTMLResponse)
async def inbox_detail(
    job_id: UUID,
    request: Request,
    _user: str = Depends(require_session),
) -> HTMLResponse:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(_DETAIL_SQL, (job_id,))
        job = cur.fetchone()
        if not job:
            return templates.TemplateResponse(
                request, "votes/error.html", {"message": "Job not found."}, status_code=404
            )
        cur.execute(
            "SELECT vote, freetext, source, created_at FROM feedback "
            "WHERE job_id = %s ORDER BY created_at DESC",
            (job_id,),
        )
        feedbacks = cur.fetchall()

    csrf = get_csrf_token(request)
    resp = templates.TemplateResponse(
        request,
        "inbox/detail.html",
        {"job": job, "feedbacks": feedbacks, "csrf_token": csrf},
    )
    set_csrf_cookie(resp, csrf)
    return resp


@router.post("/inbox/{job_id}/feedback", response_class=HTMLResponse)
async def inbox_feedback(
    job_id: UUID,
    request: Request,
    freetext: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "CSRF check failed."}, status_code=403
        )

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO feedback (job_id, vote, source, freetext) "
            "VALUES (%s, 'up'::vote_kind, 'webapp', %s)",
            (job_id, freetext.strip() or None),
        )
        conn.commit()

    return RedirectResponse(url=f"/inbox/{job_id}", status_code=303)  # type: ignore[return-value]
