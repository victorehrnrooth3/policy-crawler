"""Vote-link and magic-link routes.

GET  /v/{action}/{token}    — record a vote from an email link
POST /v/feedback/{token}    — attach free-text to a recently cast vote
GET  /m/{token}             — consume a magic link and establish a session
POST /auth/magic-link       — request a new magic link (sends email via Resend)
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

import resend
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from policy_crawler.config import get_settings
from policy_crawler.db import connection
from policy_crawler.digest.tokens import MAGIC_LINK_TOKEN_TTL, make_token, verify_token
from policy_crawler.webapp.auth import (
    get_csrf_token,
    require_session,
    set_csrf_cookie,
    set_session,
    verify_csrf,
)
from policy_crawler.webapp.deps import templates

router = APIRouter()
log = logging.getLogger(__name__)

_VALID_ACTIONS = {"up", "down", "save"}


@router.get("/v/{action}/{token}", response_class=HTMLResponse)
async def cast_vote(action: str, token: str, request: Request) -> HTMLResponse:
    if action not in _VALID_ACTIONS:
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "Unknown vote action."}, status_code=400
        )

    payload = verify_token(token, "vote")
    if not payload:
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "Token invalid or expired."}, status_code=400
        )

    job_id_str: str = payload.get("job_id", "")
    nonce: str = payload.get("nonce", "")
    try:
        job_id = UUID(job_id_str)
    except ValueError:
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "Malformed token payload."}, status_code=400
        )

    job_title: str | None = None
    already_recorded = False

    with connection() as conn, conn.cursor() as cur:
        # Atomically claim the nonce — if 0 rows affected, it's already been used
        cur.execute(
            "INSERT INTO consumed_tokens (nonce) VALUES (%s) ON CONFLICT (nonce) DO NOTHING",
            (nonce,),
        )
        if cur.rowcount == 0:
            already_recorded = True
        else:
            cur.execute(
                "INSERT INTO feedback (job_id, vote, source) "
                "VALUES (%s, %s::vote_kind, 'email_link')",
                (job_id, action),
            )
            cur.execute("SELECT title FROM jobs WHERE id = %s", (job_id,))
            row = cur.fetchone()
            job_title = row["title"] if row else None
        conn.commit()

    if already_recorded:
        return templates.TemplateResponse(request, "votes/already_recorded.html", {})

    csrf = get_csrf_token(request)
    resp = templates.TemplateResponse(
        request,
        "votes/confirmed.html",
        {
            "action": action,
            "job_title": job_title or "this role",
            "token": token,
            "csrf_token": csrf,
        },
    )
    set_csrf_cookie(resp, csrf)
    set_session(resp, get_settings().digest_to_email or "user", request)
    return resp


@router.post("/v/feedback/{token}", response_class=HTMLResponse)
async def submit_feedback(
    token: str,
    request: Request,
    freetext: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
) -> HTMLResponse:
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "CSRF check failed."}, status_code=403
        )

    payload = verify_token(token, "vote")
    if not payload:
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "Token invalid or expired."}, status_code=400
        )

    job_id_str: str = payload.get("job_id", "")
    nonce: str = payload.get("nonce", "")
    try:
        job_id = UUID(job_id_str)
    except ValueError:
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "Malformed token payload."}, status_code=400
        )

    window_ok = False
    with connection() as conn, conn.cursor() as cur:
        # Allow updates within 30 minutes of the original click
        cur.execute(
            "SELECT 1 FROM consumed_tokens WHERE nonce = %s "
            "AND consumed_at >= now() - interval '30 minutes'",
            (nonce,),
        )
        if cur.fetchone():
            window_ok = True
            cur.execute(
                "UPDATE feedback SET freetext = %s "
                "WHERE id = (SELECT id FROM feedback WHERE job_id = %s "
                "AND source = 'email_link' ORDER BY created_at DESC LIMIT 1)",
                (freetext.strip() or None, job_id),
            )
        conn.commit()

    return templates.TemplateResponse(
        request, "votes/feedback_thanks.html", {"expired": not window_ok}
    )


@router.get("/m/{token}", response_class=HTMLResponse)
async def consume_magic_link(token: str, request: Request) -> HTMLResponse:
    payload = verify_token(token, "magic_link")
    if not payload:
        return templates.TemplateResponse(
            request,
            "votes/error.html",
            {"message": "Magic link invalid or expired."},
            status_code=400,
        )

    email = get_settings().digest_to_email or "user"
    job_id_str: str | None = payload.get("job_id")
    redirect_to = f"/inbox/{job_id_str}" if job_id_str else "/inbox"

    resp = RedirectResponse(url=redirect_to, status_code=303)
    set_session(resp, email, request)
    return resp  # type: ignore[return-value]


@router.post("/auth/magic-link", response_class=HTMLResponse)
async def request_magic_link(
    request: Request,
    csrf_token: Annotated[str, Form()] = "",
) -> HTMLResponse:
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "CSRF check failed."}, status_code=403
        )

    settings = get_settings()
    to_email = settings.digest_to_email
    if not to_email:
        return templates.TemplateResponse(
            request,
            "auth/link_sent.html",
            {"message": "DIGEST_TO_EMAIL not configured."},
            status_code=500,
        )

    token = make_token({"purpose": "session"}, "magic_link", MAGIC_LINK_TOKEN_TTL)
    base_url = (settings.webapp_base_url or "").rstrip("/")
    link = f"{base_url}/m/{token}"

    if settings.resend_api_key:
        try:
            resend.api_key = settings.resend_api_key
            resend.Emails.send(
                {
                    "from": settings.digest_from_email or "noreply@resend.dev",
                    "to": [to_email],
                    "subject": "Policy Crawler — your login link",
                    "text": f"Click to log in:\n{link}\n\nExpires in 30 days.",
                }
            )
        except Exception:
            log.exception("Failed to send magic link email")

    return templates.TemplateResponse(request, "auth/link_sent.html", {"link": link})


# ── Webapp vote buttons (authenticated, CSRF-protected) ──────────────────────


@router.post("/v/webapp/{job_id}/{action}", response_class=HTMLResponse)
async def webapp_vote(
    job_id: UUID,
    action: str,
    request: Request,
    csrf_token: Annotated[str, Form()] = "",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    if action not in _VALID_ACTIONS:
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "Unknown vote action."}, status_code=400
        )
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "CSRF check failed."}, status_code=403
        )

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO feedback (job_id, vote, source) VALUES (%s, %s::vote_kind, 'webapp')",
            (job_id, action),
        )
        conn.commit()

    return RedirectResponse(url=f"/inbox/{job_id}", status_code=303)  # type: ignore[return-value]
