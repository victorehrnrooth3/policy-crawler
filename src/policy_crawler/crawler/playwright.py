from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime

import structlog

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, absolute_url

logger = structlog.get_logger(__name__)


class PlaywrightFetcher(Fetcher):
    kind = "playwright"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        try:
            from playwright.sync_api import sync_playwright  # lazy import
        except ImportError as exc:
            raise RuntimeError(
                "playwright not installed; run: pip install policy-crawler[playwright]"
            ) from exc

        selectors = source["fetcher_config"].get("selectors") or {}
        list_sel = selectors.get("list_selector")
        title_sel = selectors.get("title_selector")
        url_sel = selectors.get("url_selector")

        if not all([list_sel, title_sel, url_sel]):
            logger.info("playwright.no_selectors", source=source["name"])
            return

        base = source["careers_url"]
        now = datetime.now(UTC)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(base, wait_until="networkidle")

                for item in page.query_selector_all(list_sel):
                    title_node = item.query_selector(title_sel)
                    if not title_node:
                        continue
                    title = title_node.inner_text().strip()
                    if not title:
                        continue

                    url_node = item.query_selector(url_sel)
                    href = (url_node.get_attribute("href") or "") if url_node else ""
                    abs = absolute_url(href, base)
                    if not abs:
                        continue

                    canonical_id = hashlib.sha1(abs.encode()).hexdigest()
                    yield RawJob(
                        canonical_id=canonical_id,
                        url=abs,
                        title=title,
                        company=source["name"],
                        seen_at=now,
                    )
            finally:
                browser.close()
