"""Shared types and base class for all fetchers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

# ── Type alias for a row from the sources table (returned as dict by psycopg) ──

SourceRow = dict[str, Any]

# ── Shared HTTP client ──────────────────────────────────────────────────────────

_USER_AGENT = "policy-crawler/0.1 (+https://github.com/victorehrnrooth3/policy-crawler)"

http = httpx.Client(
    timeout=30.0,
    follow_redirects=True,
    headers={"User-Agent": _USER_AGENT},
)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout))


retry_http = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)

# ── RawJob — what every fetcher returns ────────────────────────────────────────


class RawJob(BaseModel):
    canonical_id: str
    url: str
    title: str
    company: str | None = None
    location_raw: str | None = None
    description_raw: str | None = None
    description_html: str | None = None
    posting_type: str = "unknown"
    compensation: dict[str, Any] | None = None
    seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extra: dict[str, Any] = Field(default_factory=dict)


# ── Fetcher ABC ─────────────────────────────────────────────────────────────────


class Fetcher(ABC):
    kind: ClassVar[str]

    @abstractmethod
    def fetch(self, source: SourceRow) -> Iterable[RawJob]: ...

    def configure(self, source: SourceRow) -> dict[str, Any]:
        raise NotImplementedError(f"{self.__class__.__name__} does not support configure()")


# ── Helper ──────────────────────────────────────────────────────────────────────


def absolute_url(href: str, base: str) -> str:
    """Return an absolute URL, resolving *href* relative to *base*."""
    if not href:
        return ""
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(base, href)
