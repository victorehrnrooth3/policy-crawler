from __future__ import annotations

import os
from pathlib import Path

import pytest

from policy_crawler.db import connection, get_pool
from policy_crawler.seed import load_yaml, upsert_sources

_SOURCES_YAML = Path(__file__).parents[1] / "data" / "sources.yaml"


@pytest.fixture(autouse=True)
def _reset_pool() -> None:
    get_pool.cache_clear()


def test_yaml_parses() -> None:
    """data/sources.yaml must parse and Pydantic-validate without errors."""
    seeds = load_yaml(_SOURCES_YAML)
    assert len(seeds) >= 80, f"Expected >= 80 sources, got {len(seeds)}"


@pytest.mark.skipif(
    not os.environ.get("NEON_DATABASE_URL"),
    reason="NEON_DATABASE_URL not set; skipping live DB test",
)
def test_upsert_idempotent() -> None:
    """A second upsert must not change the row count in sources."""
    seeds = load_yaml(_SOURCES_YAML)
    upsert_sources(seeds)

    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM sources")
        row1 = cur.fetchone()
    assert row1 is not None
    count1 = row1["n"]

    upsert_sources(seeds)

    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM sources")
        row2 = cur.fetchone()
    assert row2 is not None
    count2 = row2["n"]

    assert count1 == count2, f"Row count changed from {count1} to {count2} on second upsert"
