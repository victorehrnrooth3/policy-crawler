from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache
from typing import Any, cast

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from policy_crawler.config import get_settings


@cache
def get_pool() -> ConnectionPool[psycopg.Connection[dict[str, Any]]]:
    settings = get_settings()
    if not settings.neon_database_url:
        raise RuntimeError("NEON_DATABASE_URL not set")
    # row_factory is passed via kwargs (ConnectionPool has no direct parameter for it),
    # so we cast to propagate the row type to pyright.
    return cast(
        "ConnectionPool[psycopg.Connection[dict[str, Any]]]",
        ConnectionPool(
            settings.neon_database_url,
            min_size=1,
            max_size=4,
            max_idle=180,  # recycle before Neon's ~5-min server-side idle timeout
            check=ConnectionPool.check_connection,  # validate before handing out
            kwargs={
                "row_factory": dict_row,
                # TCP keepalives stop Neon's pooler from dropping a connection
                # that idles while the ranker spends 10+ min on LLM calls between
                # the SELECT (fetch unscored) and the write-back. Probes start
                # after 30s idle, repeat every 10s, give up after 5 failures.
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            },
            open=True,
        ),
    )


@contextmanager
def connection() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    with get_pool().connection() as conn:
        yield conn


def health_check() -> bool:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        row = cur.fetchone()
    return row is not None and row["ok"] == 1
