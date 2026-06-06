"""FastAPI application factory for the policy-crawler webapp."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from policy_crawler.webapp.auth import AuthRequired
from policy_crawler.webapp.deps import templates
from policy_crawler.webapp.routes import inbox, manual, profile, sources, status, votes

_STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Policy Crawler", docs_url=None, redoc_url=None)

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    app.include_router(votes.router)
    app.include_router(inbox.router)
    app.include_router(sources.router)
    app.include_router(profile.router)
    app.include_router(status.router)
    app.include_router(manual.router)

    @app.exception_handler(AuthRequired)
    async def _auth_required(request: Request, exc: AuthRequired) -> HTMLResponse:
        csrf = __import__("secrets").token_hex(16)
        resp = templates.TemplateResponse(
            request,
            "auth/request_link.html",
            {"csrf_token": csrf},
            status_code=401,
        )
        from policy_crawler.webapp.auth import set_csrf_cookie

        set_csrf_cookie(resp, csrf)
        return resp

    return app


app = create_app()
