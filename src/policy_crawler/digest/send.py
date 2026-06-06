"""Send the daily digest email via Resend."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import resend
import structlog

from policy_crawler.config import get_settings
from policy_crawler.digest.compose import mark_digest_sent, pick_jobs
from policy_crawler.digest.template import render_digest

logger = structlog.get_logger(__name__)

_OUT_DIR = Path("out")


def send_digest(today: date | None = None, dry_run: bool = False) -> None:
    """Pick jobs, render email, and either write to disk (dry_run) or send via Resend."""
    today = today or date.today()
    settings = get_settings()

    if not settings.token_hmac_secret:
        raise RuntimeError("TOKEN_HMAC_SECRET not set")

    jobs = pick_jobs(today)
    html, text, subject = render_digest(today, jobs, settings)

    if dry_run:
        _OUT_DIR.mkdir(exist_ok=True)
        html_path = _OUT_DIR / f"digest-{today}.html"
        txt_path = _OUT_DIR / f"digest-{today}.txt"
        html_path.write_text(html, encoding="utf-8")
        txt_path.write_text(text, encoding="utf-8")
        logger.info("digest.dry_run.written", html=str(html_path), txt=str(txt_path))
        print(f"Dry run: wrote {html_path} and {txt_path}")
        return

    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY not set")
    if not settings.digest_from_email:
        raise RuntimeError("DIGEST_FROM_EMAIL not set")
    if not settings.digest_to_email:
        raise RuntimeError("DIGEST_TO_EMAIL not set")

    resend.api_key = settings.resend_api_key
    try:
        r = resend.Emails.send(
            {
                "from": settings.digest_from_email,
                "to": [settings.digest_to_email],
                "subject": subject,
                "html": html,
                "text": text,
            }
        )
        email_id = getattr(r, "id", None)
        logger.info("digest.sent", subject=subject, jobs=len(jobs), email_id=email_id)
    except Exception as exc:
        logger.error("digest.send_error", error=str(exc))
        raise

    if jobs:
        mark_digest_sent([j["id"] for j in jobs])


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Send the daily policy job digest.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--send", action="store_true", help="Send via Resend.")
    group.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Render to out/digest-YYYY-MM-DD.html and .txt instead of sending.",
    )
    args = parser.parse_args()
    send_digest(dry_run=args.dry_run)
    sys.exit(0)


if __name__ == "__main__":
    main()
