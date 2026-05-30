"""Crawler orchestrator: crawl_all() walks enabled sources and writes to jobs."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import structlog

from policy_crawler.crawler.dedupe import dedup_key
from policy_crawler.crawler.normalize import normalize
from policy_crawler.crawler.registry import get_fetcher
from policy_crawler.db import connection

logger = structlog.get_logger(__name__)

# ── SQL ─────────────────────────────────────────────────────────────────────────

_SELECT_SOURCES = """
SELECT id, name, careers_url, homepage_url, category, fetcher_kind,
       fetcher_config, geography_tags, priority, enabled,
       last_checked_at, last_success_at, notes
FROM sources
WHERE enabled = true
{extra}
ORDER BY priority DESC, name
"""

_INSERT_RUN = """
INSERT INTO runs (kind, status) VALUES (%s::run_kind, 'started') RETURNING id
"""

_UPDATE_RUN = """
UPDATE runs
SET status = %s::run_status,
    finished_at = now(),
    jobs_seen = %s,
    jobs_new = %s,
    llm_calls_count = 0,
    total_cost_usd = 0,
    error = %s
WHERE id = %s
"""

_CHECK_EXISTING_JOB = """
SELECT id, title, location_raw,
       md5(coalesce(description_raw, '')) AS desc_hash
FROM jobs
WHERE source_id = %s AND canonical_id = %s
"""

_UPSERT_JOB = """
INSERT INTO jobs (
    source_id, canonical_id, url, title, company,
    location_raw, location_parsed, remote_policy, seniority, posting_type,
    description_raw, description_clean, compensation,
    first_seen_at, last_seen_at
) VALUES (
    %s, %s, %s, %s, %s,
    %s, %s::jsonb, %s::remote_policy, %s::seniority, %s::posting_type,
    %s, %s, %s::jsonb,
    now(), now()
)
ON CONFLICT (source_id, canonical_id) DO UPDATE SET
    url              = EXCLUDED.url,
    title            = EXCLUDED.title,
    company          = EXCLUDED.company,
    location_raw     = EXCLUDED.location_raw,
    location_parsed  = EXCLUDED.location_parsed,
    remote_policy    = EXCLUDED.remote_policy,
    seniority        = EXCLUDED.seniority,
    posting_type     = EXCLUDED.posting_type,
    description_raw  = EXCLUDED.description_raw,
    description_clean = EXCLUDED.description_clean,
    compensation     = EXCLUDED.compensation,
    last_seen_at     = now()
RETURNING id, (xmax = 0) AS is_insert
"""

_INSERT_JOB_VERSION = """
INSERT INTO job_versions (job_id, title, location_raw, description_clean, change_summary)
VALUES (%s, %s, %s, %s, %s)
"""

_UPDATE_SOURCE_TIMES = """
UPDATE sources
SET last_checked_at = now(),
    last_success_at = CASE WHEN %s THEN now() ELSE last_success_at END
WHERE id = %s
"""


# ── Summary ─────────────────────────────────────────────────────────────────────


@dataclass
class RunSummary:
    run_id: UUID | None = None
    jobs_seen: int = 0
    jobs_new: int = 0
    jobs_updated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if not self.errors:
            return "succeeded"
        if self.jobs_seen > 0:
            return "partial"
        return "failed"


# ── Core helpers ─────────────────────────────────────────────────────────────────


def _content_hash(text: str | None) -> str:
    return hashlib.md5((text or "").encode()).hexdigest()


def _upsert_job(cur: Any, job: dict[str, Any], existing_keys: set[str]) -> tuple[UUID, bool, bool]:
    """Insert or update one job. Returns (job_id, is_new, content_changed)."""
    source_id = job["source_id"]
    canonical_id = job["canonical_id"]

    # Check existing state before upsert so we can detect content changes
    cur.execute(_CHECK_EXISTING_JOB, (source_id, canonical_id))
    existing = cur.fetchone()

    params = (
        source_id,
        canonical_id,
        job.get("url", ""),
        job.get("title", ""),
        job.get("company"),
        job.get("location_raw"),
        json.dumps(job.get("location_parsed") or {}),
        job.get("remote_policy", "unknown"),
        job.get("seniority", "unknown"),
        job.get("posting_type", "role"),
        job.get("description_raw"),
        job.get("description_clean"),
        json.dumps(job.get("compensation")) if job.get("compensation") else None,
    )
    cur.execute(_UPSERT_JOB, params)
    row = cur.fetchone()
    job_id: UUID = row["id"]
    is_new: bool = bool(row["is_insert"])

    content_changed = False
    if not is_new and existing:
        new_hash = _content_hash(job.get("description_raw"))
        if (
            existing["title"] != job.get("title")
            or existing["location_raw"] != job.get("location_raw")
            or existing["desc_hash"] != new_hash
        ):
            content_changed = True
            cur.execute(
                _INSERT_JOB_VERSION,
                (
                    existing["id"],
                    existing["title"],
                    existing["location_raw"],
                    job.get("description_clean"),
                    "Content updated",
                ),
            )

    return job_id, is_new, content_changed


# ── crawl_all ────────────────────────────────────────────────────────────────────


def crawl_all(
    kind: str = "manual",
    only_source_name: str | None = None,
    only_kinds: set[str] | None = None,
) -> RunSummary:
    summary = RunSummary()

    # Determine which sources to crawl
    extra_clauses: list[str] = []
    if only_source_name:
        extra_clauses.append(f"AND name = '{only_source_name.replace(chr(39), chr(39) * 2)}'")
    if only_kinds:
        kinds_sql = ", ".join(f"'{k}'" for k in only_kinds)
        extra_clauses.append(f"AND fetcher_kind IN ({kinds_sql})")

    sources_sql = _SELECT_SOURCES.format(extra=" ".join(extra_clauses))

    with connection() as conn, conn.cursor() as cur:
        # Open run row
        cur.execute(_INSERT_RUN, (kind,))
        row = cur.fetchone()
        assert row is not None
        run_id: UUID = row["id"]
        summary.run_id = run_id

        # Load enabled sources (dynamic WHERE clause, no user input)
        cur.execute(sources_sql)  # type: ignore[arg-type]
        sources = cur.fetchall()

    logger.info("crawl.start", run_id=str(run_id), sources=len(sources), kind=kind)

    # Global cross-source dedupe key set
    seen_dedup_keys: set[str] = set()

    for source in sources:
        source_name = source["name"]
        fetcher_kind = source["fetcher_kind"]
        log = logger.bind(source=source_name, fetcher=fetcher_kind)

        try:
            fetcher = get_fetcher(fetcher_kind)
        except KeyError as exc:
            summary.errors.append(f"{source_name}: {exc}")
            log.warning("crawl.unknown_fetcher")
            continue

        raw_jobs = []
        try:
            raw_jobs = list(fetcher.fetch(source))
        except Exception as exc:
            summary.errors.append(f"{source_name}: {exc}")
            log.warning("crawl.fetch_error", error=str(exc))

        summary.jobs_seen += len(raw_jobs)

        # Normalize + dedupe
        normalized: list[dict[str, Any]] = []
        for raw in raw_jobs:
            try:
                job = normalize(raw, source)
                dk = dedup_key(job)
                if dk in seen_dedup_keys:
                    continue
                seen_dedup_keys.add(dk)
                normalized.append(job)
            except Exception as exc:
                summary.errors.append(f"{source_name}/{raw.canonical_id}: {exc}")

        # Write to DB
        source_ok = True
        with connection() as conn, conn.cursor() as cur:
            for job in normalized:
                try:
                    _job_id, is_new, changed = _upsert_job(cur, job, seen_dedup_keys)
                    if is_new:
                        summary.jobs_new += 1
                    elif changed:
                        summary.jobs_updated += 1
                except Exception as exc:
                    summary.errors.append(f"{source_name}/{job.get('canonical_id')}: {exc}")
                    source_ok = False

            # Warn if source went silent
            prev_seen = source.get("last_success_at")
            if len(raw_jobs) == 0 and prev_seen is not None:
                log.warning("crawl.source_silent", last_success=str(prev_seen))

            cur.execute(_UPDATE_SOURCE_TIMES, (source_ok and len(raw_jobs) > 0, source["id"]))

        log.info(
            "crawl.source_done",
            raw=len(raw_jobs),
            new=summary.jobs_new,
            errors=len([e for e in summary.errors if source_name in e]),
        )

    # Close run row
    error_text = "\n".join(summary.errors[:200]) if summary.errors else None
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            _UPDATE_RUN,
            (summary.status, summary.jobs_seen, summary.jobs_new, error_text, run_id),
        )

    logger.info(
        "crawl.done",
        run_id=str(run_id),
        status=summary.status,
        jobs_seen=summary.jobs_seen,
        jobs_new=summary.jobs_new,
        errors=len(summary.errors),
    )
    return summary


# ── CLI ──────────────────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the policy-crawler job pipeline.")
    parser.add_argument(
        "--kind",
        default="manual",
        choices=["daily", "weekly_discovery", "weekly_self_update", "manual"],
        help="Run kind recorded in the runs table (default: manual)",
    )
    parser.add_argument("--source", metavar="NAME", help="Crawl only this source (by name)")
    parser.add_argument(
        "--fetcher-kind",
        metavar="KIND",
        action="append",
        dest="fetcher_kinds",
        help="Restrict to this fetcher_kind (may be repeated)",
    )
    parser.add_argument(
        "--configure-generic-html",
        action="store_true",
        help="Print selector suggestions for generic_html sources (no DB writes)",
    )
    args = parser.parse_args()

    if args.configure_generic_html:
        _configure_generic_html()
        return

    only_kinds = set(args.fetcher_kinds) if args.fetcher_kinds else None
    summary = crawl_all(
        kind=args.kind,
        only_source_name=args.source,
        only_kinds=only_kinds,
    )
    print(
        f"Run {summary.run_id}: status={summary.status}, "
        f"seen={summary.jobs_seen}, new={summary.jobs_new}, "
        f"errors={len(summary.errors)}"
    )
    if summary.errors:
        for err in summary.errors[:20]:
            print(f"  {err}", file=sys.stderr)
    # Close pool cleanly to avoid psycopg_pool thread-stop warnings on exit
    import contextlib

    from policy_crawler.db import get_pool as _get_pool

    with contextlib.suppress(Exception):
        _get_pool().close()
    sys.exit(0 if summary.status in ("succeeded", "partial") else 1)


def _configure_generic_html() -> None:
    """Print selector suggestions for unconfigured generic_html sources."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT name, careers_url FROM sources "
            "WHERE fetcher_kind = 'generic_html' AND enabled = true "
            "AND (fetcher_config->>'selectors' IS NULL OR fetcher_config = '{}')"
        )
        sources = cur.fetchall()

    if not sources:
        print("No unconfigured generic_html sources.")
        return

    for s in sources:
        print(f"\n{s['name']}: {s['careers_url']}")
        print("  → Visit the page and inspect the job listing HTML to fill in:")
        print("    fetcher_config:")
        print("      selectors:")
        print("        list_selector:  <CSS selector for each job card>")
        print("        title_selector: <CSS selector for the title within the card>")
        print("        url_selector:   <CSS selector for the link within the card>")
        print("        location_selector: <optional>")


if __name__ == "__main__":
    main()
