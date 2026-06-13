"""Sources management routes.

GET  /sources                           — three-tab view (active / suggested / rejected)
POST /sources/suggested/{id}/approve    — approve + insert into sources
POST /sources/suggested/{id}/reject     — reject a suggestion
POST /sources/suggested/{id}/snooze     — snooze a suggestion
GET  /sources/{id}/edit                 — edit form for an active source
POST /sources/{id}/edit                 — apply edits
"""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from policy_crawler.db import connection
from policy_crawler.webapp.auth import get_csrf_token, require_session, set_csrf_cookie, verify_csrf
from policy_crawler.webapp.deps import templates

router = APIRouter()


@router.get("/sources", response_class=HTMLResponse)
async def sources_list(
    request: Request,
    tab: str = "active",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, careers_url, category, fetcher_kind, priority, enabled, "
            "last_checked_at, last_success_at FROM sources ORDER BY name"
        )
        active = cur.fetchall()

        cur.execute(
            "SELECT id, name, careers_url, category, fetcher_kind, rationale, status, proposed_at "
            "FROM suggested_sources WHERE status = 'pending' ORDER BY proposed_at DESC"
        )
        pending = cur.fetchall()

        cur.execute(
            "SELECT id, name, careers_url, status, decided_at "
            "FROM suggested_sources WHERE status IN ('rejected', 'snoozed') "
            "ORDER BY decided_at DESC NULLS LAST LIMIT 50"
        )
        rejected = cur.fetchall()

    csrf = get_csrf_token(request)
    resp = templates.TemplateResponse(
        request,
        "sources/list.html",
        {
            "active": active,
            "pending": pending,
            "rejected": rejected,
            "tab": tab,
            "csrf_token": csrf,
        },
    )
    set_csrf_cookie(resp, csrf)
    return resp


@router.post("/sources/suggested/{source_id}/approve", response_class=HTMLResponse)
async def approve_suggestion(
    source_id: UUID,
    request: Request,
    csrf_token: Annotated[str, Form()] = "",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "CSRF check failed."}, status_code=403
        )

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE suggested_sources SET status = 'approved', decided_at = now() WHERE id = %s",
            (source_id,),
        )
        cur.execute(
            """
            INSERT INTO sources (name, careers_url, category, fetcher_kind, approved_by_me, enabled)
            SELECT name, careers_url,
                   COALESCE(category, 'think_tank')::source_category,
                   COALESCE(fetcher_kind, 'camoufox')::fetcher_kind,
                   true, true
            FROM suggested_sources WHERE id = %s
            """,
            (source_id,),
        )
        conn.commit()

    return RedirectResponse(url="/sources?tab=active", status_code=303)  # type: ignore[return-value]


@router.post("/sources/suggested/{source_id}/reject", response_class=HTMLResponse)
async def reject_suggestion(
    source_id: UUID,
    request: Request,
    csrf_token: Annotated[str, Form()] = "",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "CSRF check failed."}, status_code=403
        )

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE suggested_sources SET status = 'rejected', decided_at = now() WHERE id = %s",
            (source_id,),
        )
        conn.commit()

    return RedirectResponse(url="/sources?tab=pending", status_code=303)  # type: ignore[return-value]


@router.post("/sources/suggested/{source_id}/snooze", response_class=HTMLResponse)
async def snooze_suggestion(
    source_id: UUID,
    request: Request,
    csrf_token: Annotated[str, Form()] = "",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "CSRF check failed."}, status_code=403
        )

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE suggested_sources SET status = 'snoozed', decided_at = now() WHERE id = %s",
            (source_id,),
        )
        conn.commit()

    return RedirectResponse(url="/sources?tab=pending", status_code=303)  # type: ignore[return-value]


@router.get("/sources/{source_id}/edit", response_class=HTMLResponse)
async def source_edit_form(
    source_id: UUID,
    request: Request,
    _user: str = Depends(require_session),
) -> HTMLResponse:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM sources WHERE id = %s", (source_id,))
        source = cur.fetchone()

    if not source:
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "Source not found."}, status_code=404
        )

    csrf = get_csrf_token(request)
    resp = templates.TemplateResponse(
        request,
        "sources/edit.html",
        {
            "source": source,
            "config_json": json.dumps(source["fetcher_config"], indent=2),
            "csrf_token": csrf,
        },
    )
    set_csrf_cookie(resp, csrf)
    return resp


@router.post("/sources/{source_id}/edit", response_class=HTMLResponse)
async def source_edit_save(
    source_id: UUID,
    request: Request,
    fetcher_kind: Annotated[str, Form()],
    fetcher_config: Annotated[str, Form()] = "{}",
    priority: Annotated[int, Form()] = 3,
    geography_tags: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "on",
    csrf_token: Annotated[str, Form()] = "",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "CSRF check failed."}, status_code=403
        )

    try:
        config_parsed = json.loads(fetcher_config or "{}")
    except json.JSONDecodeError:
        return templates.TemplateResponse(
            request,
            "votes/error.html",
            {"message": "Invalid JSON in fetcher config."},
            status_code=400,
        )

    tags = [t.strip() for t in geography_tags.split(",") if t.strip()]
    is_enabled = enabled == "on"

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE sources SET fetcher_kind = %s::fetcher_kind, fetcher_config = %s, "
            "priority = %s, geography_tags = %s, enabled = %s WHERE id = %s",
            (fetcher_kind, json.dumps(config_parsed), priority, tags, is_enabled, source_id),
        )
        conn.commit()

    return RedirectResponse(url="/sources?tab=active", status_code=303)  # type: ignore[return-value]
