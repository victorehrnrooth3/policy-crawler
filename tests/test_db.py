from __future__ import annotations

import os

import pytest

from policy_crawler.db import connection, get_pool, health_check

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEON_DATABASE_URL"),
    reason="NEON_DATABASE_URL not set; skipping live DB smoke test",
)


@pytest.fixture(autouse=True)
def _reset_pool() -> None:
    get_pool.cache_clear()


def test_health_check() -> None:
    assert health_check() is True


def test_temp_table_roundtrip() -> None:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE _smoke (n int)")
        cur.execute("INSERT INTO _smoke VALUES (1), (2), (3) RETURNING n")
        inserted = [r["n"] for r in cur.fetchall()]
        cur.execute("SELECT sum(n) AS s FROM _smoke")
        row = cur.fetchone()
    assert sorted(inserted) == [1, 2, 3]
    assert row is not None
    assert row["s"] == 6
