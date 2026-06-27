"""Inbox routes — five job views (inbox/recommended/saved/all/archived), detail,
and a unified per-job / bulk action endpoint (save, archive, delete, votes)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import psycopg.sql as pgsql
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from policy_crawler.config import get_settings
from policy_crawler.db import connection
from policy_crawler.webapp.auth import (
    get_csrf_token,
    require_session,
    set_csrf_cookie,
    verify_csrf,
)
from policy_crawler.webapp.deps import templates

router = APIRouter()

# Nav order for the job views; also the set of valid ?view targets.
VIEW_ORDER = ("inbox", "recommended", "saved", "all", "archived")
_VIEW_PATH = {
    "inbox": "/inbox",
    "recommended": "/recommended",
    "saved": "/saved",
    "all": "/all",
    "archived": "/archived",
}

# op -> whether it sets/clears a job state column and/or records a feedback vote.
_VALID_OPS = {"up", "down", "save", "unsave", "archive", "unarchive", "delete"}
_VOTE_OPS = {"up": "up", "down": "down", "save": "save"}  # ops that log a feedback row

_SELECT_COLS = pgsql.SQL("""
SELECT
    j.id, j.title, j.company, j.location_raw, j.url, j.posting_type,
    j.pass1_score, j.pass1_confidence, j.pass2_score,
    j.pass2_reason_to_consider, j.pass2_concerns, j.pass2_recommended_action,
    j.digest_sent_at, j.first_seen_at, j.saved_at, j.archived_at,
    s.name AS source_name, s.category AS source_category
FROM jobs j
JOIN sources s ON j.source_id = s.id
WHERE {where}
ORDER BY {order}
LIMIT {limit}
""")

_DETAIL_SQL = pgsql.SQL("""
SELECT
    j.*,
    s.name AS source_name, s.careers_url AS source_url, s.category AS source_category
FROM jobs j
JOIN sources s ON j.source_id = s.id
WHERE j.id = %s
""")

# Per-view counts in one pass (for the nav badges).
_COUNTS_SQL = """
SELECT
  count(*) FILTER (
      WHERE digest_sent_at IS NOT NULL AND digest_sent_at >= now() - interval '14 days'
        AND deleted_at IS NULL AND archived_at IS NULL) AS inbox,
  count(*) FILTER (
      WHERE pass1_score IS NOT NULL AND COALESCE(pass2_score, pass1_score) >= %s
        AND deleted_at IS NULL AND archived_at IS NULL) AS recommended,
  count(*) FILTER (
      WHERE saved_at IS NOT NULL AND deleted_at IS NULL AND archived_at IS NULL) AS saved,
  count(*) FILTER (
      WHERE pass1_score IS NOT NULL AND deleted_at IS NULL AND archived_at IS NULL) AS all,
  count(*) FILTER (WHERE archived_at IS NOT NULL AND deleted_at IS NULL) AS archived
FROM jobs
"""

_SCORE_ORDER = pgsql.SQL("COALESCE(j.pass2_score, j.pass1_score) DESC NULLS LAST")

# Vote-state filter options (the list dropdown). Filtered in-memory after fetch.
_FEEDBACK_STATES = {"unrated", "up", "down"}
_LATEST_VOTES_SQL = (
    "SELECT DISTINCT ON (job_id) job_id, vote FROM feedback "
    "WHERE job_id = ANY(%s::uuid[]) ORDER BY job_id, created_at DESC"
)


def _view_query(view: str, threshold: int) -> tuple[pgsql.Composed, pgsql.SQL, int]:
    """Return (where, order, limit) for *view*. All views exclude deleted jobs."""
    if view == "inbox":
        where = pgsql.SQL(
            "j.digest_sent_at IS NOT NULL AND j.digest_sent_at >= now() - interval '14 days' "
            "AND j.deleted_at IS NULL AND j.archived_at IS NULL"
        )
        return pgsql.Composed([where]), _SCORE_ORDER, 200
    if view == "recommended":
        where = pgsql.SQL(
            "j.pass1_score IS NOT NULL "
            "AND COALESCE(j.pass2_score, j.pass1_score) >= {} "
            "AND j.deleted_at IS NULL AND j.archived_at IS NULL"
        ).format(pgsql.Literal(threshold))
        return pgsql.Composed([where]), _SCORE_ORDER, 300
    if view == "saved":
        where = pgsql.SQL(
            "j.saved_at IS NOT NULL AND j.deleted_at IS NULL AND j.archived_at IS NULL"
        )
        return pgsql.Composed([where]), pgsql.SQL("j.saved_at DESC"), 300
    if view == "archived":
        where = pgsql.SQL("j.archived_at IS NOT NULL AND j.deleted_at IS NULL")
        return pgsql.Composed([where]), pgsql.SQL("j.archived_at DESC"), 300
    # all
    where = pgsql.SQL(
        "j.pass1_score IS NOT NULL AND j.deleted_at IS NULL AND j.archived_at IS NULL"
    )
    return pgsql.Composed([where]), _SCORE_ORDER, 300


def _render_list(request: Request, view: str, feedback_state: str) -> HTMLResponse:
    threshold = get_settings().recommended_score_threshold
    where, order, limit = _view_query(view, threshold)
    sql = _SELECT_COLS.format(where=where, order=order, limit=pgsql.Literal(limit))

    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        jobs = cur.fetchall()
        cur.execute(_COUNTS_SQL, (threshold,))
        counts = cur.fetchone()

        if feedback_state in _FEEDBACK_STATES and jobs:
            cur.execute(_LATEST_VOTES_SQL, ([j["id"] for j in jobs],))
            votes_by_job = {str(r["job_id"]): r["vote"] for r in cur.fetchall()}
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
            "view": view,
            "counts": counts,
            "feedback_state": feedback_state,
            "csrf_token": csrf,
        },
    )
    set_csrf_cookie(resp, csrf)
    return resp


@router.get("/inbox", response_class=HTMLResponse)
async def inbox_list(
    request: Request, feedback_state: str = "", _user: str = Depends(require_session)
) -> HTMLResponse:
    return _render_list(request, "inbox", feedback_state)


@router.get("/recommended", response_class=HTMLResponse)
async def recommended_list(
    request: Request, feedback_state: str = "", _user: str = Depends(require_session)
) -> HTMLResponse:
    return _render_list(request, "recommended", feedback_state)


@router.get("/saved", response_class=HTMLResponse)
async def saved_list(
    request: Request, feedback_state: str = "", _user: str = Depends(require_session)
) -> HTMLResponse:
    return _render_list(request, "saved", feedback_state)


@router.get("/all", response_class=HTMLResponse)
async def all_list(
    request: Request, feedback_state: str = "", _user: str = Depends(require_session)
) -> HTMLResponse:
    return _render_list(request, "all", feedback_state)


@router.get("/archived", response_class=HTMLResponse)
async def archived_list(
    request: Request, feedback_state: str = "", _user: str = Depends(require_session)
) -> HTMLResponse:
    return _render_list(request, "archived", feedback_state)


def _csrf_error(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "votes/error.html", {"message": "CSRF check failed."}, status_code=403
    )


def _redirect_to(view: str) -> RedirectResponse:
    return RedirectResponse(url=_VIEW_PATH.get(view, "/inbox"), status_code=303)


def _apply_op(cur: Any, op: str, ids: list[UUID]) -> None:
    if op == "save":
        cur.execute(
            "UPDATE jobs SET saved_at = now() WHERE id = ANY(%s) AND saved_at IS NULL", (ids,)
        )
    elif op == "unsave":
        cur.execute("UPDATE jobs SET saved_at = NULL WHERE id = ANY(%s)", (ids,))
    elif op == "archive":
        cur.execute(
            "UPDATE jobs SET archived_at = now() WHERE id = ANY(%s) AND archived_at IS NULL", (ids,)
        )
    elif op == "unarchive":
        cur.execute("UPDATE jobs SET archived_at = NULL WHERE id = ANY(%s)", (ids,))
    elif op == "delete":
        # View-only soft delete: no feedback signal (decluttering, not a judgment).
        cur.execute(
            "UPDATE jobs SET deleted_at = now() WHERE id = ANY(%s) AND deleted_at IS NULL", (ids,)
        )

    if op in _VOTE_OPS:
        cur.execute(
            "INSERT INTO feedback (job_id, vote, source) "
            "SELECT unnest(%s::uuid[]), %s::vote_kind, 'webapp'",
            (ids, _VOTE_OPS[op]),
        )


@router.post("/inbox/action", response_class=HTMLResponse)
async def inbox_action(
    request: Request,
    op: Annotated[str, Form()] = "",
    view: Annotated[str, Form()] = "inbox",
    job_ids: Annotated[list[str], Form()] = [],  # noqa: B006 - FastAPI Form default
    csrf_token: Annotated[str, Form()] = "",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    if not verify_csrf(request, csrf_token):
        return _csrf_error(request)
    if op not in _VALID_OPS:
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "Unknown action."}, status_code=400
        )
    try:
        ids = [UUID(j) for j in job_ids]
    except ValueError:
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "Bad job id."}, status_code=400
        )
    if ids:
        with connection() as conn, conn.cursor() as cur:
            _apply_op(cur, op, ids)
            conn.commit()
    return _redirect_to(view if view in _VIEW_PATH else "inbox")  # type: ignore[return-value]


@router.post("/inbox/archived/delete-all", response_class=HTMLResponse)
async def archived_delete_all(
    request: Request,
    csrf_token: Annotated[str, Form()] = "",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    if not verify_csrf(request, csrf_token):
        return _csrf_error(request)
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET deleted_at = now() "
            "WHERE archived_at IS NOT NULL AND deleted_at IS NULL"
        )
        conn.commit()
    return _redirect_to("archived")  # type: ignore[return-value]


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
        return _csrf_error(request)

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO feedback (job_id, vote, source, freetext) "
            "VALUES (%s, 'up'::vote_kind, 'webapp', %s)",
            (job_id, freetext.strip() or None),
        )
        conn.commit()

    return RedirectResponse(url=f"/inbox/{job_id}", status_code=303)  # type: ignore[return-value]
