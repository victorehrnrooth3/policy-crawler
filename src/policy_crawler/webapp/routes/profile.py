"""Profile routes — view current preference profile and manage proposed changes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from policy_crawler.db import connection
from policy_crawler.webapp.auth import get_csrf_token, require_session, set_csrf_cookie, verify_csrf
from policy_crawler.webapp.deps import templates

router = APIRouter()

_PROFILE_PATH = Path(__file__).parents[5] / "data" / "profile.yaml"


def _load_profile() -> dict[object, object]:
    if _PROFILE_PATH.exists():
        return yaml.safe_load(_PROFILE_PATH.read_text(encoding="utf-8")) or {}
    return {}


@router.get("/profile", response_class=HTMLResponse)
async def profile_view(
    request: Request,
    _user: str = Depends(require_session),
) -> HTMLResponse:
    profile = _load_profile()

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, diff, rationale_per_change, status, proposed_at "
            "FROM proposed_profile_changes WHERE status = 'pending' ORDER BY proposed_at DESC"
        )
        pending_changes = cur.fetchall()

    csrf = get_csrf_token(request)
    resp = templates.TemplateResponse(
        request,
        "profile/index.html",
        {"profile": profile, "pending_changes": pending_changes, "csrf_token": csrf},
    )
    set_csrf_cookie(resp, csrf)
    return resp


@router.post("/profile/changes/{change_id}/approve", response_class=HTMLResponse)
async def approve_change(
    change_id: UUID,
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
            "UPDATE proposed_profile_changes "
            "SET status = 'applied', applied_at = now() WHERE id = %s",
            (change_id,),
        )
        conn.commit()

    return RedirectResponse(url="/profile", status_code=303)  # type: ignore[return-value]


@router.post("/profile/changes/{change_id}/reject", response_class=HTMLResponse)
async def reject_change(
    change_id: UUID,
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
            "UPDATE proposed_profile_changes SET status = 'rejected' WHERE id = %s",
            (change_id,),
        )
        conn.commit()

    return RedirectResponse(url="/profile", status_code=303)  # type: ignore[return-value]
