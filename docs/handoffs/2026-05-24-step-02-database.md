# Handoff — Step 02 (Database), paused 2026-05-24

This document captures the full context of the session that planned (but did not execute) Step 02. It is meant to be self-contained: a new agent reading only this file, plus the standard docs in [`docs/00-overview.md`](../00-overview.md) through [`docs/04-conventions.md`](../04-conventions.md) and [`docs/steps/02-database.md`](../steps/02-database.md), should be able to pick up exactly where this session left off, on a different machine, with no further context required.

## Why paused

Step 02 requires applying a Postgres migration against a Neon free-tier database. The work laptop (`OneDrive - McKinsey & Company` indicates a McKinsey-issued device) cannot establish a Postgres connection to Neon:

- DNS to `ep-curly-frost-al3jqzl0-pooler.c-3.eu-central-1.aws.neon.tech` resolves to three AWS IPs.
- `Test-NetConnection ... -Port 5432` returns `TcpTestSucceeded : True` — so the TCP-level path is open.
- Every `psycopg.connect(...)` attempt (5 URL variants tested: pooled / direct / with-without `channel_binding=require` / `sslmode=verify-full`) fails with `server closed the connection unexpectedly` the moment psycopg sends Postgres's `SSLRequest` packet.

That fingerprint — TCP open, application-layer connection reset on first Postgres protocol byte — is the textbook signature of a **corporate egress proxy doing L7 / DPI inspection** that allow-lists HTTPS but drops Postgres.

The user's local source IP was `10.17.28.28` (private RFC-1918), consistent with a corporate VPN/LAN. The user verified that the Neon URLs "work" in Neon's own browser dashboard — but the Neon SQL Editor talks to Postgres from Neon's infrastructure (not from the user's laptop), so it bypasses the laptop's egress filter and proves nothing about local reachability.

## What is already done (pushed to `origin`)

- **`main`** (`62b66b7`) — the original docs roadmap commit.
- **`step-01-scaffolding`** (`1587dac`) — full Step 01 deliverable, audited, all 5 acceptance commands exit 0. Files: `pyproject.toml`, `ruff.toml`, `pyrightconfig.json`, `.env.example`, `src/policy_crawler/{__init__.py, config.py, models.py}`, `tests/{__init__.py, test_smoke.py}`, README install/test snippet, and two newly-discovered gotchas appended to `docs/04-conventions.md`.
- **`step-02-database`** (this branch) — Step 02 **handoff documentation only**, no Step 02 code yet. This is the branch you want to start from on the new machine.

`step-02-database` is branched off `step-01-scaffolding`, so pulling this one branch on the personal laptop gets you both Step 01's code AND this handoff content in a single fetch.

## Three options for the next agent

In order of "fastest progress":

1. **Mobile tether or home wifi (recommended).** Disconnect from corporate VPN, tether the laptop to a phone hotspot (or work on a personal device on home wifi). Re-probe Neon — almost certainly works. Execute the inlined Step 02 plan below as a single session. Total time: ~30 min including verification.
2. **Defer live verification to GitHub Actions.** Build all Step 02 code, make the live test auto-skip when DB is unreachable (not just when env is unset), commit + push. The migration only gets applied in CI later (Step 08), or when the user is on a clean network. Downside: schema correctness is unverified until that happens.
3. **Wait.** Hold the entire step until the user is on a non-corporate network. Don't write code yet. Update `docs/STATUS.md` when picking it back up.

The user asked to pause and continue on personal laptop, so option (1) is the assumed path.

## Inputs the next agent needs

1. A `.env` file at the repo root with both Neon URLs populated:
   ```
   NEON_DATABASE_URL=postgresql://USER:PASS@ep-XXX-pooler.<region>.aws.neon.tech/neondb?sslmode=require
   NEON_DATABASE_URL_DIRECT=postgresql://USER:PASS@ep-XXX.<region>.aws.neon.tech/neondb?sslmode=require
   ```
   The work-laptop `.env` is gitignored and not on the new machine. The Neon project itself already exists (named `policy-crawler`, region `aws-eu-central-1`, single DB `neondb`); the URLs can be re-copied from the Neon dashboard.

   The `channel_binding=require` query param Neon's UI generates by default is fine — psycopg with bundled libpq 18 supports it on a clean network. Strip it only if you see "channel binding type ... is not supported" errors.

2. A working Python 3.12 venv: `python -m venv .venv` then `pip install -e .[dev]`. (Step 01 README has this verbatim under "Install & test".)

3. Network egress to `*.aws.neon.tech:5432`. Re-verify with the one-liner below before writing any code:

   ```powershell
   .\.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; import psycopg; load_dotenv(); psycopg.connect(os.environ['NEON_DATABASE_URL_DIRECT'], connect_timeout=30).close(); print('ok')"
   ```

   If it prints `ok`, proceed. If it prints `server closed the connection unexpectedly`, you're still behind a corporate filter — switch networks before doing anything else.

## Step 02 plan (inlined, ready to execute)

Read [`docs/steps/02-database.md`](../steps/02-database.md) first — this plan implements exactly what that step file specifies, with the implementation choices already made.

### Branch & scope

You're already on `step-02-database`. One commit at the end. No edits to anything Step 01 built; this step **adds** files (plus a README.md append and possibly one gotchas append to `docs/04-conventions.md`).

### Files to create

#### `migrations/0001_init.sql`

Single SQL file, applied in one transaction by the runner. Structure in order:

1. `CREATE EXTENSION IF NOT EXISTS pgcrypto;` (for `gen_random_uuid()`).
2. **12 enum types** (per [`docs/steps/02-database.md`](../steps/02-database.md) § Schema):
   - `source_category` — `think_tank`, `asset_manager_policy_institute`, `geopolitical_risk`, `corporate_policy_tech`, `corporate_policy_defense`, `corporate_policy_energy`, `igo`, `government`, `predoc_program`, `phd_program`, `fellowship`.
   - `fetcher_kind` — `greenhouse`, `lever`, `ashby`, `workable`, `smartrecruiters`, `workday_json`, `rss`, `sitemap`, `generic_html`, `playwright`, `manual`.
   - `posting_type` — `role`, `fellowship`, `predoc`, `program_call`, `internal_rotation`, `unknown`.
   - `remote_policy` — `onsite`, `hybrid`, `remote`, `unknown`.
   - `seniority` — `intern`, `early_career`, `mid`, `senior`, `lead`, `exec`, `unknown`.
   - `vote_kind` — `up`, `down`, `save`, `applied`, `hidden`.
   - `vote_source` — `email_link`, `webapp`, `auto`.
   - `suggestion_status` — `pending`, `approved`, `rejected`, `snoozed`.
   - `change_status` — `pending`, `applied`, `rejected`.
   - `run_kind` — `daily`, `weekly_discovery`, `weekly_self_update`, `manual`.
   - `run_status` — `started`, `succeeded`, `failed`, `partial`.
   - `llm_call_kind` — `pass1`, `pass2`, `discovery`, `self_update`, `manual_extract`.
3. **`set_updated_at()` trigger function**:

   ```sql
   CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
   LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$;
   ```

4. **8 tables**, each with `id uuid primary key default gen_random_uuid()`, `created_at timestamptz not null default now()`, plus `updated_at` + trigger where applicable. Columns from [`docs/01-architecture.md`](../01-architecture.md) § Data model:
   - `sources` (updated_at + trigger; `priority int not null default 3`; `enabled bool not null default true`; `approved_by_me bool not null default true`; `fetcher_config jsonb not null default '{}'`; `geography_tags text[] not null default '{}'`).
   - `jobs` (updated_at + trigger; FK `source_id uuid not null references sources(id) on delete cascade`; `UNIQUE (source_id, canonical_id)`; `pass1_confidence text` — **not** an enum because `low`/`med`/`high` are not in the enum list).
   - `job_versions` (FK `job_id`; columns: `title text`, `location_raw text`, `description_clean text`, `change_summary text`, `observed_at timestamptz not null default now()`; **no** `updated_at`).
   - `feedback` (FK `job_id`; `vote vote_kind not null`; `source vote_source not null`; `freetext text`; **no** `updated_at`).
   - `suggested_sources` (updated_at + trigger; `status suggestion_status not null default 'pending'`; `proposed_at timestamptz not null default now()`; `decided_at timestamptz`).
   - `proposed_profile_changes` (updated_at + trigger; `diff jsonb not null`; `rationale_per_change jsonb not null`; `status change_status not null default 'pending'`).
   - `runs` (**no** updated_at; `kind run_kind not null`; `status run_status not null default 'started'`; counters int default 0; `total_cost_usd numeric(10,4) not null default 0`; `error text`).
   - `llm_calls` (**no** updated_at; FK `run_id uuid references runs(id) on delete set null`; `model text not null`; `input_tokens int`, `output_tokens int`; `cost_usd numeric(10,6) not null default 0`; `kind llm_call_kind not null`; `latency_ms int`; `error text`).
5. **Indexes** exactly as the step file lists:
   - `CREATE INDEX ON sources (enabled, category);`
   - `CREATE INDEX ON sources (fetcher_kind);`
   - jobs unique constraint above already creates the `(source_id, canonical_id)` index.
   - `CREATE INDEX ON jobs (last_seen_at DESC);`
   - `CREATE INDEX ON jobs (pass1_score DESC NULLS LAST);`
   - `CREATE INDEX ON jobs (pass2_score DESC NULLS LAST);`
   - `CREATE INDEX ON jobs (digest_sent_at) WHERE digest_sent_at IS NULL;` (partial)
   - `CREATE INDEX ON feedback (job_id, created_at DESC);`
   - `CREATE INDEX ON suggested_sources (status);`
   - `CREATE INDEX ON proposed_profile_changes (status);`
   - `CREATE INDEX ON runs (kind, started_at DESC);`
   - `CREATE INDEX ON llm_calls (run_id);`
6. **Triggers** — `CREATE TRIGGER trg_<table>_updated_at BEFORE UPDATE ON <table> FOR EACH ROW EXECUTE FUNCTION set_updated_at();` on the four `updated_at` tables: `sources`, `jobs`, `suggested_sources`, `proposed_profile_changes`.

#### `migrations/_apply.py`

~50 lines. Pseudocode (use this almost verbatim):

```python
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
```

Key choices:
- Uses **direct** URL — pgbouncer rejects DDL on prepared-statement protocol; migrations must bypass the pooler.
- One transaction per file (commit only after the file fully applies; on failure, rollback before re-raise so `_migrations` stays clean).
- `glob("*.sql")` excludes `_apply.py` automatically.

#### `src/policy_crawler/db.py`

```python
from __future__ import annotations

from contextlib import contextmanager
from functools import cache
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from policy_crawler.config import get_settings


@cache
def get_pool() -> ConnectionPool:
    settings = get_settings()
    if not settings.neon_database_url:
        raise RuntimeError("NEON_DATABASE_URL not set")
    return ConnectionPool(
        settings.neon_database_url,
        min_size=1,
        max_size=4,
        kwargs={"row_factory": dict_row},
        open=True,
    )


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn:
        yield conn


def health_check() -> bool:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        row = cur.fetchone()
    return bool(row and row.get("?column?") == 1)
```

Key choices:
- Pool created lazily via `@cache` — never at import time (Vercel cold-start gotcha per step file).
- Uses **pooled** URL (Neon's `-pooler` host).
- `min_size=1, max_size=4` per step note ("Neon's pooler is the connection ceiling, not us").
- `dict_row` set as the default row factory on every connection from the pool.

#### `tests/test_db.py`

```python
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
        total = cur.fetchone()["s"]
    assert sorted(inserted) == [1, 2, 3]
    assert total == 6
```

- `CREATE TEMP TABLE` auto-drops at connection end; no explicit cleanup.
- Step file mentions monkeypatching the pool to a unique-named test schema with teardown — that pattern can wait until Step 04+ when real CRUD tests arrive. `TEMP TABLE` is the simpler equivalent for the smoke test.

### Files to edit

#### `README.md`

Append a "Database setup" section after "Install & test":

```markdown
## Database setup

1. Create a free-tier Neon project named `policy-crawler` at neon.tech.
2. Copy the **pooled** connection string (host contains `-pooler.`) into `.env` as `NEON_DATABASE_URL`, and the **direct** one as `NEON_DATABASE_URL_DIRECT`.
3. Apply the schema:

   `python migrations/_apply.py`

   Expect: "Applied 0001_init.sql" then "All migrations up to date."

4. Verify in Neon's SQL editor that all 8 tables and 12 enums exist.

Re-running `python migrations/_apply.py` is a no-op.
```

#### `docs/04-conventions.md`

Append to the "Things agents reliably get wrong on this project" list — only if you hit them during execution; otherwise skip:

- **Migrations must use `NEON_DATABASE_URL_DIRECT`.** Neon's pgbouncer (the `-pooler` host) runs in transaction pooling mode and silently breaks DDL that depends on session state. The migration runner reads the direct URL; the app pool reads the pooled URL. Mixing them up surfaces as "prepared statement does not exist" errors hundreds of lines into a migration.
- **`get_pool()` is `@cache`-d.** Tests that touch the DB must `get_pool.cache_clear()` (autouse fixture) — same pattern as `get_settings`, same reason.
- **Corporate egress filters block port 5432.** Document this if it ever bites the user again: TCP handshake succeeds, but the Postgres `SSLRequest` upgrade is reset by an inspecting proxy. Workarounds: mobile tether, home wifi, or run the migration from CI.

### Verification

Code-only (works without Neon):

```
ruff format .          # one pass to normalize freshly-written files
ruff check .
ruff format --check .
pyright
pytest -q
```

`pytest -q` should show **3 passed, 2 skipped** if `NEON_DATABASE_URL` is unset, or **4 passed** if set and reachable.

Live (requires a network that can reach Neon):

```
python migrations/_apply.py     # -> "Applied 0001_init.sql" then "All migrations up to date."
python migrations/_apply.py     # -> "All migrations up to date." (idempotent)
pytest -q tests/test_db.py      # -> 2 passed
```

Then in Neon's SQL editor:

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;
-- expect: _migrations, feedback, job_versions, jobs, llm_calls,
--         proposed_profile_changes, runs, sources, suggested_sources

SELECT typname FROM pg_type WHERE typtype = 'e' ORDER BY typname;
-- expect 12 enums
```

### Commit message (single commit, this branch)

```
feat: add Neon schema + migration runner + connection layer (step 02)

Files: migrations/0001_init.sql, migrations/_apply.py,
src/policy_crawler/db.py, tests/test_db.py, README.md (Database
setup section), and (if hit during build) appended gotchas in
docs/04-conventions.md.

Acceptance verified locally:
  python migrations/_apply.py   -> Applied 0001_init.sql / up to date
  ruff check / format / pyright -> all clean
  pytest -q                     -> N passed
```

### Out of scope (per step file)

- Seeding `sources` rows (Step 03).
- Any real reads/writes beyond the smoke test (later steps).
- A `/health` webapp endpoint (Step 11).
- `job_versions` retention policy (followup in step file).

## Session summary

A condensed log of what happened so the next agent knows what's already been decided.

### Step 01 execution

User instructed the agent to execute Step 01 per the agent preamble in `docs/04-conventions.md`. Agent read docs 00/01/03/04 plus `docs/steps/01-scaffolding.md`, presented a plan, then executed:

- Created branch `step-01-scaffolding`.
- Wrote `pyproject.toml` (with `anthropic>=0.40` deviation justified by `docs/03-tech-stack.md`'s "unpinned beyond major" rule, inline-commented).
- Wrote `ruff.toml` with `line-ending = "auto"` (LF-hard-coding broke `ruff format --check` on Windows checkouts where `core.autocrlf=true` converts to CRLF; inline-commented).
- Wrote `pyrightconfig.json`, `.env.example`, `src/policy_crawler/__init__.py`, `config.py`, `models.py`, `tests/__init__.py`, `test_smoke.py`.
- Appended Install & test snippet to `README.md`.
- Created venv, ran `pip install -e .[dev]` (one transient network retry needed), all 4 acceptance commands exited 0.
- Appended two newly-discovered gotchas to `docs/04-conventions.md` (the `ruff format` ordering rule and the `get_settings()` `@cache` test pattern).
- Committed `feat: scaffold Python project for step 01` and pushed.

### Step 01 audit

User then asked the agent to verify the push and audit Step 01. Audit: all 11 deliverables present, all 5 acceptance commands green, all implementation notes honored, two intentional deviations documented inline. Push verified — `origin/step-01-scaffolding` matches local HEAD `1587dac`. Verdict: complete, on-spec, ready for Step 02.

### Step 02 planning

User chose the "Guide me through Neon provisioning" option. Agent presented a plan (this document is the durable version of that plan) that includes a manual pre-flight (Neon project creation, copying URLs into `.env`) and the full set of code deliverables. Plan was approved.

### Step 02 execution attempt

User said `.env` was populated and explicitly authorized push. Agent ran a connectivity probe:

1. First probe: `dotenv` reported the URLs as empty. The Cursor IDE's read tool showed populated values, but PowerShell's `Select-String` on the on-disk file confirmed `chars after '=' -> 0` on both NEON lines. Diagnosis: the IDE had the file open with unsaved edits in its buffer.
2. User then "made the whole folder save to this device and verified that the links work." Second probe: URLs were now visible to `dotenv`. DNS resolved to three AWS IPs. `Test-NetConnection ... -Port 5432` returned `TcpTestSucceeded : True`. But every `psycopg.connect` (5 variants — pooled / direct / no channel_binding / sslmode=verify-full) failed with `server closed the connection unexpectedly` mid-handshake.
3. Diagnosed as corporate egress / L7 proxy filtering. User confirmed they'd continue on a personal laptop.

The probe script was deleted after use. Git working tree is clean. Nothing is half-built.

## What's NOT in this handoff (and shouldn't be)

- The user's actual Neon credentials (in `.env`, gitignored, work-laptop only — re-copy from Neon dashboard on the new machine).
- The user's CV or personal context (in `docs/02-personal-context.md`, which is committed but only relevant for Steps 03 / 05 / 09 / 10).
- Any half-written Step 02 code (none exists; agent never started building).
