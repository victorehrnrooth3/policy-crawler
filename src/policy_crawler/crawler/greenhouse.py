from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import structlog

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, http, retry_http

logger = structlog.get_logger(__name__)


class GreenhouseFetcher(Fetcher):
    kind = "greenhouse"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        board = source["fetcher_config"].get("board")
        if not board:
            logger.warning("greenhouse.missing_board", source=source["name"])
            return

        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        try:
            response = retry_http(http.get)(url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("greenhouse.fetch_error", source=source["name"], error=str(exc))
            return

        now = datetime.now(UTC)
        for job in response.json().get("jobs", []):
            yield RawJob(
                canonical_id=str(job["id"]),
                url=job.get("absolute_url", ""),
                title=job.get("title", ""),
                company=source["name"],
                location_raw=(job.get("location") or {}).get("name"),
                description_html=job.get("content") or None,
                seen_at=now,
            )
