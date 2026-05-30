from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import UTC, datetime

import structlog

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, http, retry_http

logger = structlog.get_logger(__name__)

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_DEFAULT_FILTER = r"/jobs?/|/careers?/|/opening|/position|/vacancy"


class SitemapFetcher(Fetcher):
    kind = "sitemap"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        sitemap_url = source["fetcher_config"].get("sitemap_url") or source["careers_url"]
        url_filter = source["fetcher_config"].get("url_filter_regex", _DEFAULT_FILTER)
        pattern = re.compile(url_filter, re.IGNORECASE)

        try:
            response = retry_http(http.get)(sitemap_url)
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except Exception as exc:
            logger.warning("sitemap.fetch_error", source=source["name"], error=str(exc))
            return

        now = datetime.now(UTC)
        for loc_elem in root.findall(".//sm:url/sm:loc", _NS):
            url = (loc_elem.text or "").strip()
            if not url or not pattern.search(url):
                continue
            canonical_id = hashlib.sha1(url.encode()).hexdigest()
            title = url.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ")
            yield RawJob(
                canonical_id=canonical_id,
                url=url,
                title=title,
                company=source["name"],
                seen_at=now,
            )
