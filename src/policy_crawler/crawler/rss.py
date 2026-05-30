from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime

import feedparser
import structlog

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow

logger = structlog.get_logger(__name__)


class RSSFetcher(Fetcher):
    kind = "rss"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        rss_url = source["fetcher_config"].get("rss_url") or source["careers_url"]
        try:
            feed = feedparser.parse(rss_url)
        except Exception as exc:
            logger.warning("rss.parse_error", source=source["name"], error=str(exc))
            return

        if feed.bozo and not feed.entries:
            logger.warning("rss.bad_feed", source=source["name"])
            return

        now = datetime.now(UTC)
        for entry in feed.entries:
            guid = str(entry.get("id") or entry.get("link") or "")
            canonical_id = hashlib.sha1(guid.encode()).hexdigest()
            link = str(entry.get("link") or "")
            title = str(entry.get("title") or "")
            summary = entry.get("summary")
            yield RawJob(
                canonical_id=canonical_id,
                url=link,
                title=title,
                company=source["name"],
                description_html=str(summary) if summary else None,
                seen_at=now,
            )
