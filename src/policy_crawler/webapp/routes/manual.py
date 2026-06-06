"""Manual job-entry route.

GET  /manual  — paste URL + free-text description form
POST /manual  — fetch URL, call Sonnet for structured extraction, persist
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

import httpx
from anthropic import Anthropic
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from selectolax.parser import HTMLParser

from policy_crawler.config import get_settings
from policy_crawler.db import connection
from policy_crawler.webapp.auth import get_csrf_token, require_session, set_csrf_cookie, verify_csrf
from policy_crawler.webapp.deps import templates

router = APIRouter()
log = logging.getLogger(__name__)

_EXTRACT_TOOL = {
    "name": "extract_job",
    "description": "Extract structured job details from a posting.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Job title"},
            "company": {"type": "string", "description": "Company or organisation name"},
            "location_raw": {"type": "string", "description": "Location as written in the posting"},
            "posting_type": {
                "type": "string",
                "enum": [
                    "role",
                    "fellowship",
                    "predoc",
                    "program_call",
                    "internal_rotation",
                    "unknown",
                ],
            },
            "description_clean": {
                "type": "string",
                "description": "Concise markdown summary of the posting (200–400 words)",
            },
        },
        "required": ["title", "company", "location_raw", "posting_type", "description_clean"],
    },
}

_MANUAL_SOURCE_NAME = "Manual entry"


def _get_or_create_manual_source(conn: object) -> UUID:
    from psycopg import Connection as PgConn

    c: PgConn[dict[str, object]] = conn  # type: ignore[assignment]
    with c.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE name = %s", (_MANUAL_SOURCE_NAME,))
        row = cur.fetchone()
        if row:
            return UUID(str(row["id"]))
        cur.execute(
            "INSERT INTO sources (name, careers_url, category, fetcher_kind, approved_by_me) "
            "VALUES (%s, 'manual', 'think_tank'::source_category, 'manual'::fetcher_kind, true) "
            "RETURNING id",
            (_MANUAL_SOURCE_NAME,),
        )
        new_row = cur.fetchone()
        c.commit()
        return UUID(str(new_row["id"]))  # type: ignore[index]


def _fetch_text(url: str) -> str:
    try:
        r = httpx.get(
            url, timeout=15, follow_redirects=True, headers={"User-Agent": "policy-crawler/1.0"}
        )
        r.raise_for_status()
        tree = HTMLParser(r.text)
        for tag in tree.css("script, style, nav, footer, header"):
            tag.decompose()
        return (tree.body.text(separator="\n") if tree.body else "")[:8000]
    except Exception as exc:
        log.warning("Failed to fetch %s: %s", url, exc)
        return ""


def _extract_via_llm(url: str, page_text: str, freetext: str) -> dict[str, str]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {
            "title": url,
            "company": "Unknown",
            "location_raw": "",
            "posting_type": "unknown",
            "description_clean": freetext or page_text[:500],
        }

    client = Anthropic(api_key=settings.anthropic_api_key)
    user_content = f"URL: {url}\n\nUser note: {freetext}\n\nPage text:\n{page_text}"
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        tools=[_EXTRACT_TOOL],  # type: ignore[list-item]
        tool_choice={"type": "tool", "name": "extract_job"},
        messages=[{"role": "user", "content": user_content}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "extract_job":
            return block.input  # type: ignore[return-value]
    return {
        "title": url,
        "company": "Unknown",
        "location_raw": "",
        "posting_type": "unknown",
        "description_clean": freetext or page_text[:500],
    }


@router.get("/manual", response_class=HTMLResponse)
async def manual_form(
    request: Request,
    _user: str = Depends(require_session),
) -> HTMLResponse:
    csrf = get_csrf_token(request)
    resp = templates.TemplateResponse(
        request, "manual/form.html", {"csrf_token": csrf, "success": False, "error": None}
    )
    set_csrf_cookie(resp, csrf)
    return resp


@router.post("/manual", response_class=HTMLResponse)
async def manual_submit(
    request: Request,
    url: Annotated[str, Form()],
    freetext: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    _user: str = Depends(require_session),
) -> HTMLResponse:
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(
            request, "votes/error.html", {"message": "CSRF check failed."}, status_code=403
        )

    page_text = _fetch_text(url)
    extracted = _extract_via_llm(url, page_text, freetext)

    with connection() as conn:
        source_id = _get_or_create_manual_source(conn)
        canonical_id = url
        with conn.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(
                """
                INSERT INTO jobs (source_id, canonical_id, url, title, company,
                    location_raw, posting_type, description_clean)
                VALUES (%s, %s, %s, %s, %s, %s, %s::posting_type, %s)
                ON CONFLICT (source_id, canonical_id) DO UPDATE
                    SET title = EXCLUDED.title,
                        description_clean = EXCLUDED.description_clean,
                        last_seen_at = now()
                RETURNING id
                """,
                (
                    source_id,
                    canonical_id,
                    url,
                    extracted.get("title", url),
                    extracted.get("company", ""),
                    extracted.get("location_raw", ""),
                    extracted.get("posting_type", "unknown"),
                    extracted.get("description_clean", ""),
                ),
            )
            row = cur.fetchone()
            conn.commit()  # type: ignore[attr-defined]

        job_id = row["id"] if row else None  # type: ignore[index]

    if job_id:
        return RedirectResponse(url=f"/inbox/{job_id}", status_code=303)  # type: ignore[return-value]

    csrf = get_csrf_token(request)
    resp = templates.TemplateResponse(
        request, "manual/form.html", {"csrf_token": csrf, "success": True, "error": None}
    )
    set_csrf_cookie(resp, csrf)
    return resp
