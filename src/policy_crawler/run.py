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
import sys
from dataclasses import dataclass
from uuid import UUID

import structlog

from policy_crawler.obs.alerts import send_failure_email, send_warning_email
from policy_crawler.obs.runs import finish_run, start_run

logger = structlog.get_logger(__name__)

_KINDS = ("weekly", "daily", "weekly_discovery", "weekly_self_update")

# Email a (deduped) heads-up if at least this many sources that used to return
# jobs came back empty in one run — a sign a fetcher or board URL silently broke.
_SILENT_SOURCES_WARN_THRESHOLD = 5


@dataclass
class _PipelineSummary:
    jobs_seen: int = 0
    jobs_new: int = 0
    llm_calls_count: int = 0
    total_cost_usd: float = 0.0
    sources_silent: int = 0


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
        sources_silent=crawl_summary.sources_silent,
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
        sources_silent=crawl_summary.sources_silent,
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


# ── Cost aggregation ──────────────────────────────────────────────────────────


def _run_cost_and_calls(run_id: UUID, summary: _PipelineSummary) -> tuple[float, int]:
    """True run cost = sum of *all* llm_calls for this run.

    The crawl summary doesn't thread per-page ``crawl_extract`` cost back up, so
    re-deriving from the ``llm_calls`` table is the single source of truth and
    folds crawl + pass1/2 + discovery + self-update into one figure. Falls back
    to the threaded summary totals if the aggregate query fails — cost accounting
    must never block a run from being marked finished.
    """
    try:
        from policy_crawler.obs.cost import run_call_count, run_spend

        return run_spend(run_id), run_call_count(run_id)
    except Exception:
        logger.warning("run.cost_aggregate_failed", run_id=str(run_id))
        return summary.total_cost_usd, summary.llm_calls_count


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

        total_cost_usd, llm_calls_count = _run_cost_and_calls(run_id, summary)
        finish_run(
            run_id,
            status="succeeded",
            jobs_seen=summary.jobs_seen,
            jobs_new=summary.jobs_new,
            llm_calls_count=llm_calls_count,
            total_cost_usd=total_cost_usd,
        )
        logger.info("run.succeeded", kind=kind, run_id=str(run_id), cost=round(total_cost_usd, 4))

        if summary.sources_silent >= _SILENT_SOURCES_WARN_THRESHOLD:
            send_warning_email(
                run_id,
                f"{summary.sources_silent} sources that previously returned jobs came back "
                f"empty in the {kind} run — a fetcher or board URL may have silently broken.",
            )
    except Exception as exc:
        error_text = str(exc)
        finish_run(run_id, status="failed", error=error_text)
        logger.error("run.failed", kind=kind, run_id=str(run_id), error=error_text)
        send_failure_email(run_id, kind, error_text)
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
