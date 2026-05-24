# Step 02 — Database

## Goal

Provision a Neon Postgres database, ship the initial schema migration, and add a tiny migration runner + connection helper so later steps can read/write.

## Reading list

- `docs/01-architecture.md` (the **Data model** section — primary spec for this step)
- `docs/03-tech-stack.md` (the Neon and `psycopg` rows)
- `docs/04-conventions.md`
- `docs/steps/01-scaffolding.md`

## Inputs / prereqs

- Step 01 complete.
- A Neon account (free tier). Provision one project; name it `policy-crawler`. Create one database (default `neondb` is fine).
- Two connection strings, copied to GitHub Actions secrets and to local `.env`:
  - `NEON_DATABASE_URL` — the **pooled** connection string (host contains `-pooler`). Use this everywhere except migrations.
  - `NEON_DATABASE_URL_DIRECT` — the **direct** connection string. Use this for migrations only.

## Deliverables

- `migrations/0001_init.sql` — the schema described below. Use Postgres-native types (`text`, `timestamptz`, `jsonb`, `text[]`, custom `enum` types). Include `CREATE EXTENSION IF NOT EXISTS pgcrypto;` for `gen_random_uuid()`. Every table has `id uuid primary key default gen_random_uuid()`, `created_at timestamptz default now()`, and (where appropriate) `updated_at timestamptz default now()`. Add a generic trigger to keep `updated_at` fresh on update.
- `migrations/_apply.py` — a small Python runner that:
  - Reads `NEON_DATABASE_URL_DIRECT` from env.
  - Creates a `_migrations` table if missing (`filename text primary key, applied_at timestamptz default now()`).
  - Lists `migrations/*.sql` in lexicographic order, skips ones already applied, applies the rest in a single transaction each.
  - Prints a summary.
- `src/policy_crawler/db.py`:
  - `get_pool()` returning a cached `psycopg_pool.ConnectionPool` using `NEON_DATABASE_URL` (pooled).
  - `connection()` context manager that yields a connection from the pool, configured with `row_factory=dict_row`.
  - `health_check()` — runs `SELECT 1` and returns `True` / raises.
- `tests/test_db.py`:
  - A test (skipped if `NEON_DATABASE_URL` not set in env) that calls `health_check()` and a smoke insert/select round-trip into a temporary table that gets dropped at end of test.
- Update `.env.example` to include both connection strings if not already present.
- Update `README.md` with a "Database setup" section: how to create the Neon project, where to copy the URLs, and how to run `python migrations/_apply.py`.

## Schema (in `0001_init.sql`)

Create these enum types up front:

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

Then the tables, exactly as described in `docs/01-architecture.md` § "Data model". Index hints (add at least these):

- `sources(enabled, category)`, `sources(fetcher_kind)`.
- `jobs(source_id, canonical_id)` UNIQUE.
- `jobs(last_seen_at DESC)`, `jobs(pass1_score DESC NULLS LAST)`, `jobs(pass2_score DESC NULLS LAST)`.
- `jobs(digest_sent_at)` partial index `WHERE digest_sent_at IS NULL`.
- `feedback(job_id, created_at DESC)`.
- `suggested_sources(status)`, `proposed_profile_changes(status)`.
- `runs(kind, started_at DESC)`, `llm_calls(run_id)`.

## Acceptance criteria

```bash
# From repo root, with .env populated:
python migrations/_apply.py
# Expect output: "Applied 0001_init.sql" then "All migrations up to date."

pytest -q tests/test_db.py
# Expect: 1 passed (or 1 skipped if NEON_DATABASE_URL absent in CI)
```

After running, in Neon's SQL editor confirm:
- All 8 tables exist (`sources`, `jobs`, `job_versions`, `feedback`, `suggested_sources`, `proposed_profile_changes`, `runs`, `llm_calls`) plus `_migrations`.
- All enums exist.

Re-running `python migrations/_apply.py` is a no-op ("All migrations up to date.").

## Implementation notes

- Use plain SQL files, not Alembic. The migration runner is ~40 lines of Python.
- Wrap each migration application in a single transaction. If any statement fails, the migration is not recorded as applied.
- For enums, prefer `CREATE TYPE ... AS ENUM (...);` over check constraints — clearer error messages and easier to extend with `ALTER TYPE ... ADD VALUE`.
- `updated_at` trigger pattern (one trigger function used by all tables that need it):
  ```sql
  CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
  LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$;
  ```
- Don't try to be clever with `NULLS NOT DISTINCT` unique constraints; standard `UNIQUE (source_id, canonical_id)` is fine.
- `psycopg_pool.ConnectionPool` — set `min_size=1, max_size=4` on the pooled URL. Neon's pooler is the connection ceiling, not us.
- The pool **must not** be created at import time (Vercel cold starts will time out). Lazy-create on first `connection()` call via `functools.cache`.
- For tests, monkeypatch the pool to a throwaway pool against the same Neon URL but a unique-named test schema; drop the schema in teardown.

## Out of scope

- Seeding `sources` (Step 03).
- Any reads/writes other than the smoke tests (later steps).
- A web `/health` endpoint (Step 11).

## Followups

- Future migration: row-level retention policy on `job_versions` (e.g., keep latest 10 versions per job). Defer until table size warrants it.
