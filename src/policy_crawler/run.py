"""Top-level pipeline orchestrator.

Dispatches to the appropriate pipeline sequence by --kind, manages a single
runs row for the whole execution, and sends a failure-alert email if the run
throws an unhandled exception.

``weekly`` is the unified production pipeline (crawl all tiers + rank + digest +
source discovery + preference self-update). The standalone ``daily`` /
``weekly_discovery`` / ``weekly_self_update`` kinds remain for ad-hoc
``workflow_dispatch`` and CLI use.

Usage::

    python -m policy_crawler.run --kind weekly [--gh-pat TOKEN]
    python -m policy_crawler.run --kind daily
    python -m policy_crawler.run --kind weekly_discovery
    python -m policy_crawler.run --kind weekly_self_update [--gh-pat TOKEN]
"""

from __future__ import annotations

import contextlib
import os
import sys
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import structlog

from policy_crawler.obs.runs import finish_run, start_run

logger = structlog.get_logger(__name__)

_KINDS = ("weekly", "daily", "weekly_discovery", "weekly_self_update")


@dataclass
class _PipelineSummary:
    jobs_seen: int = 0
    jobs_new: int = 0
    llm_calls_count: int = 0
    total_cost_usd: float = 0.0


# ── Pipeline implementations ─────────────────────────────────────────────────


def _run_daily(run_id: UUID) -> _PipelineSummary:
    from policy_crawler.crawler.run import crawl_all
    from policy_crawler.digest.send import send_digest
    from policy_crawler.ranker.run import score_pending

    crawl_summary = crawl_all(run_id=run_id)
    rank_summary = score_pending(run_id=run_id)
    send_digest()
    return _PipelineSummary(
        jobs_seen=crawl_summary.jobs_seen,
        jobs_new=crawl_summary.jobs_new,
        llm_calls_count=rank_summary.pass1_scored + rank_summary.pass2_scored,
        total_cost_usd=rank_summary.total_cost_usd,
    )


def _run_weekly(run_id: UUID, gh_pat: str | None = None) -> _PipelineSummary:
    """Unified weekly pipeline: crawl (all tiers) + rank + digest + discovery + self-update.

    Discovery only proposes new sources (human approval required), and self-update
    only proposes profile changes (PR), so neither affects this run's crawl/ranking —
    they run last.
    """
    from policy_crawler.crawler.run import crawl_all
    from policy_crawler.digest.send import send_digest
    from policy_crawler.ranker.run import score_pending

    crawl_summary = crawl_all(run_id=run_id)
    rank_summary = score_pending(run_id=run_id)
    send_digest()
    disc_summary = _run_weekly_discovery(run_id)
    su_summary = _run_weekly_self_update(run_id, gh_pat=gh_pat)

    return _PipelineSummary(
        jobs_seen=crawl_summary.jobs_seen,
        jobs_new=crawl_summary.jobs_new,
        llm_calls_count=rank_summary.pass1_scored
        + rank_summary.pass2_scored
        + disc_summary.llm_calls_count
        + su_summary.llm_calls_count,
        total_cost_usd=rank_summary.total_cost_usd
        + disc_summary.total_cost_usd
        + su_summary.total_cost_usd,
    )


def _run_weekly_discovery(run_id: UUID) -> _PipelineSummary:
    from policy_crawler.discovery.run import run_discovery

    summary = run_discovery(run_id=run_id)
    return _PipelineSummary(
        llm_calls_count=1 if summary.candidates_proposed or summary.errors else 0,
        total_cost_usd=summary.cost_usd,
    )


def _run_weekly_self_update(run_id: UUID, gh_pat: str | None = None) -> _PipelineSummary:
    # gh_pat is unused at proposal time — it is only needed when the user approves
    # the change in the webapp (apply_proposed opens the PR then). Accepted here so
    # the weekly CLI signature is uniform.
    from policy_crawler.self_update.run import run_self_update

    summary = run_self_update(run_id=run_id)
    return _PipelineSummary(
        llm_calls_count=1 if (summary.ops_proposed or summary.errors) else 0,
        total_cost_usd=summary.cost_usd,
    )


# ── Failure alert ─────────────────────────────────────────────────────────────


def _send_failure_alert(kind: str, error: str) -> None:
    try:
        import resend as _resend

        from policy_crawler.config import get_settings

        settings = get_settings()
        if not (
            settings.resend_api_key and settings.digest_to_email and settings.digest_from_email
        ):
            return
        _resend.api_key = settings.resend_api_key
        today = date.today().isoformat()
        server = os.environ.get("GITHUB_SERVER_URL", "")
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        run_id_env = os.environ.get("GITHUB_RUN_ID", "")
        workflow_url = f"{server}/{repo}/actions/runs/{run_id_env}".strip("/")
        body = (
            f"Workflow: {workflow_url}\n\nError:\n{error}" if workflow_url else f"Error:\n{error}"
        )
        _resend.Emails.send(
            {
                "from": settings.digest_from_email,
                "to": [settings.digest_to_email],
                "subject": f"[policy-crawler] {kind} run failed {today}",
                "text": body,
            }
        )
    except Exception:
        logger.warning("run.failure_alert.failed")


# ── Public entry point ────────────────────────────────────────────────────────


def run(kind: str, *, gh_pat: str | None = None) -> None:
    """Open a runs row, execute the pipeline for *kind*, close the row.

    Re-raises any exception after marking the runs row as failed and sending
    a failure-alert email.
    """
    run_id = start_run(kind)
    logger.info("run.start", kind=kind, run_id=str(run_id))
    try:
        if kind == "weekly":
            summary = _run_weekly(run_id, gh_pat=gh_pat)
        elif kind == "daily":
            summary = _run_daily(run_id)
        elif kind == "weekly_discovery":
            summary = _run_weekly_discovery(run_id)
        elif kind == "weekly_self_update":
            summary = _run_weekly_self_update(run_id, gh_pat=gh_pat)
        else:
            raise ValueError(f"Unknown kind: {kind!r}")

        finish_run(
            run_id,
            status="succeeded",
            jobs_seen=summary.jobs_seen,
            jobs_new=summary.jobs_new,
            llm_calls_count=summary.llm_calls_count,
            total_cost_usd=summary.total_cost_usd,
        )
        logger.info("run.succeeded", kind=kind, run_id=str(run_id))
    except Exception as exc:
        error_text = str(exc)
        finish_run(run_id, status="failed", error=error_text)
        logger.error("run.failed", kind=kind, run_id=str(run_id), error=error_text)
        _send_failure_alert(kind, error_text)
        raise


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Orchestrate a policy-crawler pipeline run.")
    parser.add_argument(
        "--kind",
        required=True,
        choices=list(_KINDS),
        help="Which pipeline to run.",
    )
    parser.add_argument(
        "--gh-pat",
        metavar="TOKEN",
        default=None,
        dest="gh_pat",
        help="GitHub PAT for profile PR creation (weekly_self_update only).",
    )
    args = parser.parse_args()
    run(args.kind, gh_pat=args.gh_pat)

    from policy_crawler.db import get_pool

    with contextlib.suppress(Exception):
        get_pool().close()

    sys.exit(0)


if __name__ == "__main__":
    main()
