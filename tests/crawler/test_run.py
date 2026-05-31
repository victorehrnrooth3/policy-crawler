"""End-to-end run test using fake fetchers against the real DB."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

import pytest

from policy_crawler.crawler.base import RawJob, SourceRow
from policy_crawler.crawler.normalize import normalize
from policy_crawler.crawler.run import _upsert_job
from policy_crawler.db import connection, get_pool

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEON_DATABASE_URL"),
    reason="NEON_DATABASE_URL not set; skipping live DB test",
)


@pytest.fixture(autouse=True)
def _reset_pool() -> None:
    get_pool.cache_clear()


# ── Fake source inserted into the DB for the test ────────────────────────────────


@pytest.fixture
def test_source_id(request: pytest.FixtureRequest) -> Iterable[uuid.UUID]:
    """Insert a temporary source row, yield its id, then delete it."""
    sid = uuid.uuid4()
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources
                (id, name, careers_url, homepage_url, category, fetcher_kind,
                 fetcher_config, geography_tags, priority, enabled)
            VALUES
                (%s, %s, %s, NULL, 'think_tank'::source_category, 'manual'::fetcher_kind,
                 '{}'::jsonb, '{}', 3, true)
            """,
            (sid, f"_test_{request.node.name}", "https://test.invalid/jobs"),
        )
    yield sid
    with connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM jobs WHERE source_id = %s", (sid,))
        cur.execute("DELETE FROM sources WHERE id = %s", (sid,))
    get_pool.cache_clear()


# ── Helpers ──────────────────────────────────────────────────────────────────────


def _make_source_row(sid: uuid.UUID, name: str = "_test_source") -> SourceRow:
    return {
        "id": sid,
        "name": name,
        "careers_url": "https://test.invalid/jobs",
        "homepage_url": None,
        "category": "think_tank",
        "fetcher_kind": "manual",
        "fetcher_config": {},
        "geography_tags": [],
        "priority": 3,
        "enabled": True,
        "last_checked_at": None,
        "last_success_at": None,
        "notes": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }


def _raw(cid: str, title: str = "Test Role", loc: str = "London") -> RawJob:
    return RawJob(
        canonical_id=cid,
        url=f"https://test.invalid/jobs/{cid}",
        title=title,
        location_raw=loc,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────────


def test_upsert_new_job(test_source_id: uuid.UUID) -> None:
    source = _make_source_row(test_source_id)
    job = normalize(_raw("uid-1"), source)
    with connection() as conn, conn.cursor() as cur:
        _id, is_new, changed = _upsert_job(cur, job)
    assert is_new is True
    assert changed is False


def test_upsert_idempotent(test_source_id: uuid.UUID) -> None:
    source = _make_source_row(test_source_id)
    job = normalize(_raw("uid-2"), source)
    with connection() as conn, conn.cursor() as cur:
        _upsert_job(cur, job)
        _id, is_new, changed = _upsert_job(cur, job)
    assert is_new is False
    assert changed is False


def test_upsert_content_change_creates_version(test_source_id: uuid.UUID) -> None:
    source = _make_source_row(test_source_id)
    job_v1 = normalize(_raw("uid-3", title="Old Title"), source)
    with connection() as conn, conn.cursor() as cur:
        _upsert_job(cur, job_v1)

    job_v2 = normalize(_raw("uid-3", title="New Title"), source)
    with connection() as conn, conn.cursor() as cur:
        _id, is_new, changed = _upsert_job(cur, job_v2)
        cur.execute("SELECT count(*) AS n FROM job_versions WHERE job_id = %s", (_id,))
        row = cur.fetchone()
    assert is_new is False
    assert changed is True
    assert row is not None
    assert row["n"] == 1
