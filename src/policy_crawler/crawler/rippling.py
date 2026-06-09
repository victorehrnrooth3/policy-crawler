from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import structlog

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, http, retry_http

logger = structlog.get_logger(__name__)


class RipplingFetcher(Fetcher):
    """Rippling ATS via its public job-board API.

    GET https://api.rippling.com/platform/api/ats/v1/board/{org}/jobs returns a
    JSON array of {uuid, name, department:{id,label}, url, workLocation:{label}}.
    The list has no description; title + location + department are enough to screen.
    """

    kind = "rippling"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        org = source["fetcher_config"].get("org")
        if not org:
            logger.warning("rippling.missing_org", source=source["name"])
            return

        url = f"https://api.rippling.com/platform/api/ats/v1/board/{org}/jobs"
        try:
            response = retry_http(http.get)(url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("rippling.fetch_error", source=source["name"], error=str(exc))
            return

        now = datetime.now(UTC)
        for job in response.json():
            work_location = job.get("workLocation") or {}
            department = job.get("department") or {}
            yield RawJob(
                canonical_id=str(job["uuid"]),
                url=job.get("url", ""),
                title=job.get("name", ""),
                company=source["name"],
                location_raw=work_location.get("label"),
                seen_at=now,
                extra={"department": department.get("label")},
            )
