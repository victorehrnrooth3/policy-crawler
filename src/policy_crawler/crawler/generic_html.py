from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime

import structlog
from selectolax.parser import HTMLParser

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow, absolute_url, http, retry_http

logger = structlog.get_logger(__name__)


class GenericHTMLFetcher(Fetcher):
    kind = "generic_html"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        selectors = source["fetcher_config"].get("selectors") or {}
        list_sel = selectors.get("list_selector")
        title_sel = selectors.get("title_selector")
        url_sel = selectors.get("url_selector")

        if not (list_sel and title_sel and url_sel):
            logger.info(
                "generic_html.no_selectors",
                source=source["name"],
                hint="Run --configure-generic-html to set up selectors",
            )
            return

        # pyright now knows list_sel/title_sel/url_sel are str (not None)
        assert isinstance(list_sel, str)
        assert isinstance(title_sel, str)
        assert isinstance(url_sel, str)

        try:
            response = retry_http(http.get)(source["careers_url"])
            response.raise_for_status()
        except Exception as exc:
            logger.warning("generic_html.fetch_error", source=source["name"], error=str(exc))
            return

        tree = HTMLParser(response.text)
        base = source["careers_url"]
        now = datetime.now(UTC)
        location_sel = selectors.get("location_selector")
        desc_sel = selectors.get("description_selector")

        for item in tree.css(list_sel):
            title_node = item.css_first(title_sel)
            if not title_node:
                continue
            title = title_node.text(strip=True)
            if not title:
                continue

            url_node = item.css_first(url_sel)
            href = (url_node.attributes.get("href") or "") if url_node else ""
            abs = absolute_url(href, base)
            if not abs:
                continue

            canonical_id = hashlib.sha1(abs.encode()).hexdigest()

            location_raw = None
            if location_sel:
                loc_node = item.css_first(location_sel)
                if loc_node:
                    location_raw = loc_node.text(strip=True) or None

            description_html = None
            if desc_sel:
                desc_node = item.css_first(desc_sel)
                if desc_node:
                    description_html = desc_node.html

            yield RawJob(
                canonical_id=canonical_id,
                url=abs,
                title=title,
                company=source["name"],
                location_raw=location_raw,
                description_html=description_html,
                seen_at=now,
            )
