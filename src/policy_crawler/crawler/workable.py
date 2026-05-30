from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import structlog

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, http, retry_http

logger = structlog.get_logger(__name__)


class WorkableFetcher(Fetcher):
    kind = "workable"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        subdomain = source["fetcher_config"].get("subdomain")
        if not subdomain:
            logger.warning("workable.missing_subdomain", source=source["name"])
            return

        url = f"https://apply.workable.com/api/v3/accounts/{subdomain}/jobs"
        body = {
            "query": "",
            "location": [],
            "department": [],
            "worktype": [],
            "remote": [],
        }
        try:
            response = retry_http(http.post)(url, json=body)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("workable.fetch_error", source=source["name"], error=str(exc))
            return

        now = datetime.now(UTC)
        for job in response.json().get("results", []):
            shortcode = job.get("shortcode", "")
            yield RawJob(
                canonical_id=shortcode,
                url=f"https://apply.workable.com/{subdomain}/j/{shortcode}/",
                title=job.get("title", ""),
                company=source["name"],
                location_raw=job.get("location"),
                seen_at=now,
            )
