from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import structlog

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, http, retry_http

logger = structlog.get_logger(__name__)


class LeverFetcher(Fetcher):
    kind = "lever"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        company = source["fetcher_config"].get("company")
        if not company:
            logger.warning("lever.missing_company", source=source["name"])
            return

        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        try:
            response = retry_http(http.get)(url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("lever.fetch_error", source=source["name"], error=str(exc))
            return

        now = datetime.now(UTC)
        for job in response.json():
            categories = job.get("categories") or {}
            yield RawJob(
                canonical_id=job["id"],
                url=job.get("hostedUrl", ""),
                title=job.get("text", ""),
                company=source["name"],
                location_raw=categories.get("location"),
                description_html=job.get("descriptionHtml") or None,
                seen_at=now,
            )
