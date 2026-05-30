from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

MIGRATIONS_DIR = Path(__file__).parent


def main() -> int:
    load_dotenv()
    url = os.environ.get("NEON_DATABASE_URL_DIRECT")
    if not url:
        print("NEON_DATABASE_URL_DIRECT not set", file=sys.stderr)
        return 1
    with psycopg.connect(url, autocommit=False) as conn, conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "filename text primary key, applied_at timestamptz not null default now())"
        )
        conn.commit()
        cur.execute("SELECT filename FROM _migrations")
        applied = {row[0] for row in cur.fetchall()}
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        pending = [p for p in files if p.name not in applied]
        if not pending:
            print("All migrations up to date.")
            return 0
        for p in pending:
            sql = p.read_text(encoding="utf-8")
            try:
                cur.execute(sql)
                cur.execute("INSERT INTO _migrations(filename) VALUES (%s)", (p.name,))
                conn.commit()
                print(f"Applied {p.name}")
            except Exception:
                conn.rollback()
                raise
        print("All migrations up to date.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
