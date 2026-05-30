from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime

import structlog

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, http, retry_http

logger = structlog.get_logger(__name__)

# Workday tenant URL pattern
_TENANT_RE = re.compile(r"https://([^.]+)\.myworkdayjobs\.com/([^/?#]+)", re.IGNORECASE)

_LIMIT = 20


class WorkdayFetcher(Fetcher):
    kind = "workday_json"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        endpoint = self._discover_endpoint(source)
        if not endpoint:
            logger.warning("workday.no_endpoint", source=source["name"])
            return

        now = datetime.now(UTC)
        offset = 0
        while True:
            body = {"appliedFacets": {}, "limit": _LIMIT, "offset": offset, "searchText": ""}
            try:
                response = retry_http(http.post)(endpoint, json=body)
            except Exception as exc:
                logger.warning("workday.fetch_error", source=source["name"], error=str(exc))
                return

            if response.status_code != 200:
                logger.warning(
                    "workday.bad_status",
                    source=source["name"],
                    status=response.status_code,
                )
                return

            postings = response.json().get("jobPostings", [])
            for job in postings:
                path = job.get("externalPath", "")
                tenant_base = endpoint.split("/wday/")[0]
                yield RawJob(
                    canonical_id=path or job.get("title", ""),
                    url=f"{tenant_base}{path}" if path else "",
                    title=job.get("title", ""),
                    company=source["name"],
                    location_raw=job.get("locationsText"),
                    seen_at=now,
                )

            if len(postings) < _LIMIT:
                break
            offset += _LIMIT

    @staticmethod
    def _discover_endpoint(source: SourceRow) -> str | None:
        # 1. Explicit endpoint in config
        ep = source["fetcher_config"].get("endpoint")
        if ep:
            return ep

        # 2. careers_url is already a myworkdayjobs.com URL
        m = _TENANT_RE.match(source["careers_url"])
        if m:
            tenant, site = m.group(1), m.group(2)
            return f"https://{tenant}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"

        # 3. Follow redirects to discover a myworkdayjobs.com URL
        try:
            resp = http.head(source["careers_url"], follow_redirects=True, timeout=10)
            m = _TENANT_RE.match(str(resp.url))
            if m:
                tenant, site = m.group(1), m.group(2)
                return f"https://{tenant}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
        except Exception:
            pass

        return None
