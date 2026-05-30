from __future__ import annotations

from collections.abc import Iterable

from policy_crawler.crawler.base import Fetcher, RawJob, SourceRow


class ManualFetcher(Fetcher):
    """No-op fetcher. Manual jobs are added via the webapp's paste-a-URL flow."""

    kind = "manual"

    def fetch(self, source: SourceRow) -> Iterable[RawJob]:
        return iter([])
