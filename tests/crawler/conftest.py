"""VCR and shared fixtures for crawler tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    return {
        "cassette_library_dir": "tests/cassettes",
        "record_mode": "new_episodes",
        "decode_compressed_response": True,
    }


def make_source(
    *,
    name: str = "Test Source",
    careers_url: str = "https://example.com/jobs",
    category: str = "think_tank",
    fetcher_kind: str = "generic_html",
    fetcher_config: dict[str, Any] | None = None,
    geography_tags: list[str] | None = None,
    priority: int = 3,
    enabled: bool = True,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "name": name,
        "careers_url": careers_url,
        "homepage_url": None,
        "category": category,
        "fetcher_kind": fetcher_kind,
        "fetcher_config": fetcher_config or {},
        "geography_tags": geography_tags or [],
        "priority": priority,
        "enabled": enabled,
        "last_checked_at": None,
        "last_success_at": None,
        "notes": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
