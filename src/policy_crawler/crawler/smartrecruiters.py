from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import structlog

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, http, retry_http

logger = structlog.get_logger(__name__)

_LIMIT = 100


class SmartRecruitersFetcher(Fetcher):
    kind = "smartrecruiters"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        company = source["fetcher_config"].get("company")
        if not company:
            logger.warning("smartrecruiters.missing_company", source=source["name"])
            return

        now = datetime.now(UTC)
        offset = 0
        while True:
            url = (
                f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
                f"?limit={_LIMIT}&offset={offset}"
            )
            try:
                response = retry_http(http.get)(url)
                response.raise_for_status()
            except Exception as exc:
                logger.warning("smartrecruiters.fetch_error", source=source["name"], error=str(exc))
                return

            data = response.json()
            postings = data.get("content", [])

            for job in postings:
                loc = job.get("location") or {}
                city = loc.get("city", "")
                country = loc.get("country", "")
                location_raw = ", ".join(filter(None, [city, country])) or None
                yield RawJob(
                    canonical_id=job["id"],
                    url=f"https://jobs.smartrecruiters.com/{company}/{job['id']}",
                    title=job.get("name", ""),
                    company=source["name"],
                    location_raw=location_raw,
                    seen_at=now,
                )

            if len(postings) < _LIMIT:
                break
            offset += _LIMIT
