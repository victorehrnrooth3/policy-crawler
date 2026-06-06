"""Render HTML and plain-text digest emails from Jinja2 templates."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from policy_crawler.config import Settings, get_settings
from policy_crawler.digest.tokens import MAGIC_LINK_TOKEN_TTL, VOTE_TOKEN_TTL, make_token

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _effective_score(job: dict[str, Any]) -> int:
    return int(job.get("pass2_score") or job.get("pass1_score") or 0)


def _effective_reason(job: dict[str, Any]) -> str:
    return (job.get("pass2_reason_to_consider") or job.get("pass1_reason") or "").strip()


def _build_card(job: dict[str, Any], webapp_base_url: str) -> dict[str, Any]:
    job_id = str(job["id"])
    base = webapp_base_url.rstrip("/")

    up_tok = make_token({"job_id": job_id, "vote": "up"}, "vote", VOTE_TOKEN_TTL)
    down_tok = make_token({"job_id": job_id, "vote": "down"}, "vote", VOTE_TOKEN_TTL)
    save_tok = make_token({"job_id": job_id, "vote": "save"}, "vote", VOTE_TOKEN_TTL)
    magic_tok = make_token(
        {"job_id": job_id, "purpose": "review"}, "magic_link", MAGIC_LINK_TOKEN_TTL
    )

    return {
        "title": job.get("title") or "",
        "company": job.get("company") or "",
        "location_raw": job.get("location_raw") or "",
        "url": job.get("url") or "#",
        "posting_type": (job.get("posting_type") or "unknown").replace("_", " "),
        "score": _effective_score(job),
        "reason": _effective_reason(job),
        "is_borderline": bool(job.get("_borderline")),
        "up_url": f"{base}/v/up/{up_tok}",
        "down_url": f"{base}/v/down/{down_tok}",
        "save_url": f"{base}/v/save/{save_tok}",
        "review_url": f"{base}/m/{magic_tok}",
    }


def render_digest(
    today: date,
    jobs: list[dict[str, Any]],
    settings: Settings | None = None,
) -> tuple[str, str, str]:
    """Render both email variants. Returns (html, plain_text, subject)."""
    if settings is None:
        settings = get_settings()

    webapp_base_url = (settings.webapp_base_url or "http://localhost:8000").rstrip("/")
    inbox_url = f"{webapp_base_url}/inbox"

    cards = [_build_card(job, webapp_base_url) for job in jobs]
    subject = f"[{len(jobs)}] policy roles for {today.strftime('%a %d %b')}"

    ctx: dict[str, Any] = {
        "subject": subject,
        "today": today,
        "jobs": cards,
        "inbox_url": inbox_url,
    }

    html_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    txt_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)

    html = html_env.get_template("digest.html.j2").render(ctx)
    text = txt_env.get_template("digest.txt.j2").render(ctx)

    return html, text, subject
