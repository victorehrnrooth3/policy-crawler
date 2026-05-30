from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import structlog

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, http, retry_http

logger = structlog.get_logger(__name__)


class AshbyFetcher(Fetcher):
    kind = "ashby"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        org = source["fetcher_config"].get("org")
        if not org:
            logger.warning("ashby.missing_org", source=source["name"])
            return

        url = f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"
        try:
            response = retry_http(http.get)(url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("ashby.fetch_error", source=source["name"], error=str(exc))
            return

        now = datetime.now(UTC)
        # Ashby API returns "jobs" key (not "jobPostings"); "location" (not "locationName")
        for job in response.json().get("jobs", []):
            comp = job.get("compensation")
            yield RawJob(
                canonical_id=job["id"],
                url=job.get("jobUrl", ""),
                title=job.get("title", ""),
                company=source["name"],
                location_raw=job.get("location"),
                description_html=job.get("descriptionHtml") or None,
                compensation={"text": comp} if isinstance(comp, str) else comp,
                seen_at=now,
            )
