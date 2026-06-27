"""Failure / warning email alerts (step 11).

Alerts are deduped per run via ``runs.metadata.alert_sent_at``: once an alert has
been sent for a run today, repeat attempts that day are silently dropped so a
flapping run can't email 10 times. Every function here is best-effort and never
raises — an alert failure must not mask (or replace) the original error.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

import structlog

from policy_crawler.config import get_settings
from policy_crawler.db import connection

logger = structlog.get_logger(__name__)

_MAX_ERROR_LINES = 50


def _workflow_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    gh_run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not (server and repo and gh_run_id):
        return ""
    return f"{server}/{repo}/actions/runs/{gh_run_id}"


def _status_url() -> str:
    base = (get_settings().webapp_base_url or "").rstrip("/")
    return f"{base}/status" if base else ""


def _tail(text: str, lines: int = _MAX_ERROR_LINES) -> str:
    split = text.splitlines()
    return "\n".join(split[-lines:]) if len(split) > lines else text


def _already_alerted_today(run_id: UUID | None) -> bool:
    if run_id is None:
        return False
    today = datetime.now(UTC).date().isoformat()
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT metadata ->> 'alert_sent_at' AS sent FROM runs WHERE id = %s", (run_id,)
        )
        row = cur.fetchone()
    return bool(row and row["sent"] and str(row["sent"]).startswith(today))


def _mark_alerted(run_id: UUID | None) -> None:
    if run_id is None:
        return
    now = datetime.now(UTC).isoformat()
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE runs SET metadata = jsonb_set(metadata, '{alert_sent_at}', to_jsonb(%s::text)) "
            "WHERE id = %s",
            (now, run_id),
        )


def _send(subject: str, body: str) -> bool:
    settings = get_settings()
    if not (settings.resend_api_key and settings.digest_to_email and settings.digest_from_email):
        logger.warning("alert.skipped_no_email_config")
        return False
    import resend

    resend.api_key = settings.resend_api_key
    resend.Emails.send(
        {
            "from": settings.digest_from_email,
            "to": [settings.digest_to_email],
            "subject": subject,
            "text": body,
        }
    )
    return True


def send_failure_email(run_id: UUID | None, kind: str, error: str) -> bool:
    """Email DIGEST_TO_EMAIL that a *kind* run failed. Returns True if sent.

    Deduped per run per day. Never raises.
    """
    try:
        if _already_alerted_today(run_id):
            logger.info("alert.failure.deduped", run_id=str(run_id))
            return False
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        subject = f"[policy-crawler] {kind} run failed {stamp}"
        parts = [f"Run kind: {kind}", f"Run id: {run_id}"]
        workflow = _workflow_url()
        if workflow:
            parts.append(f"Workflow: {workflow}")
        status = _status_url()
        if status:
            parts.append(f"Status: {status}")
        parts.append("\nError (last 50 lines):\n" + _tail(error))
        if _send(subject, "\n".join(parts)):
            _mark_alerted(run_id)
            return True
        return False
    except Exception:
        logger.warning("alert.failure.send_failed")
        return False


def send_warning_email(run_id: UUID | None, body: str) -> bool:
    """Email a non-fatal warning (e.g. 5+ sources returned 0 jobs). Returns True if sent.

    Deduped per run per day (shares the same ``alert_sent_at`` slot as failures).
    Never raises.
    """
    try:
        if _already_alerted_today(run_id):
            logger.info("alert.warning.deduped", run_id=str(run_id))
            return False
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        subject = f"[policy-crawler] warning {stamp}"
        status = _status_url()
        full = body + (f"\n\nStatus: {status}" if status else "")
        if _send(subject, full):
            _mark_alerted(run_id)
            return True
        return False
    except Exception:
        logger.warning("alert.warning.send_failed")
        return False
