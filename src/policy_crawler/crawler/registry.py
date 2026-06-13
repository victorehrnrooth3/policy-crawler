"""Maps fetcher_kind strings to Fetcher instances."""

from __future__ import annotations

from policy_crawler.crawler.base import Fetcher

# Populated lazily to avoid circular imports at module load time.
_REGISTRY: dict[str, Fetcher] | None = None


def _build_registry() -> dict[str, Fetcher]:
    # Tier 1 = free ATS JSON APIs. Tier 2 = camoufox (browser render + Haiku
    # extraction, the long-tail strategy). Retained: generic_html (configured-
    # selector escape hatch for deferred rows) + manual (webapp-added jobs).
    # playwright/rss/sitemap were removed — zero configured sources, superseded
    # by camoufox.
    from policy_crawler.crawler.ashby import AshbyFetcher
    from policy_crawler.crawler.camoufox_llm import CamoufoxLLMFetcher
    from policy_crawler.crawler.generic_html import GenericHTMLFetcher
    from policy_crawler.crawler.greenhouse import GreenhouseFetcher
    from policy_crawler.crawler.lever import LeverFetcher
    from policy_crawler.crawler.manual import ManualFetcher
    from policy_crawler.crawler.rippling import RipplingFetcher
    from policy_crawler.crawler.smartrecruiters import SmartRecruitersFetcher
    from policy_crawler.crawler.workable import WorkableFetcher
    from policy_crawler.crawler.workday_json import WorkdayFetcher

    instances: list[Fetcher] = [
        GreenhouseFetcher(),
        LeverFetcher(),
        AshbyFetcher(),
        WorkableFetcher(),
        SmartRecruitersFetcher(),
        WorkdayFetcher(),
        RipplingFetcher(),
        CamoufoxLLMFetcher(),
        GenericHTMLFetcher(),
        ManualFetcher(),
    ]
    return {f.kind: f for f in instances}


def get_fetcher(kind: str) -> Fetcher:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    fetcher = _REGISTRY.get(kind)
    if fetcher is None:
        raise KeyError(f"No fetcher registered for kind={kind!r}")
    return fetcher
