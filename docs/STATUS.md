# Project Status

Single source of truth for "where are we right now?". Update this file at the end of every meaningful session.

## Snapshot (last updated: 2026-05-30, personal laptop)

| Step | State | Branch | Notes |
|---|---|---|---|
| 01 — Scaffolding | **Done, committed, pushed** | `step-01-scaffolding` (`1587dac`) | All 5 acceptance commands exit 0. Audited and verified. |
| 02 — Database | **Done, committed, pushed** | `step-02-database` (this branch) | Migration applied to Neon. All 5 acceptance commands exit 0. Live DB tests pass. |
| 03–11 | Not started | — | — |

## What's on disk right now (this branch)

Everything from `step-01-scaffolding`, plus Step 02 deliverables:

- `migrations/0001_init.sql` — full schema: pgcrypto extension, 12 enum types, `set_updated_at()` trigger, 8 tables, 11 indexes, 4 triggers.
- `migrations/_apply.py` — migration runner (reads `NEON_DATABASE_URL_DIRECT`, idempotent).
- `src/policy_crawler/db.py` — `get_pool()` (cached), `connection()` context manager, `health_check()`.
- `tests/test_db.py` — live DB smoke tests (skipped when `NEON_DATABASE_URL` absent).
- `README.md` — "Database setup" section added.
- `docs/04-conventions.md` — three new gotchas appended (migrations URL, `get_pool` cache, corporate egress).
- `pyproject.toml` — `requires-python` relaxed to `<3.14` (personal laptop has Python 3.13 only).

## Next concrete actions (in order)

1. Decide: open PR for `step-02-database` → `main`, or proceed directly to Step 03.
2. Step 03 — Source registry & seed: read `docs/steps/03-source-registry.md`, populate `data/sources.yaml` from `Top think tanks.xlsx` and architecture doc employer list, seed the `sources` table.

## Conventions reminder

When kicking off any step, follow the agent preamble in [`docs/04-conventions.md`](04-conventions.md) §"Agent-prompting conventions": read 00, 01, 03, 04 end-to-end, skim 02 if the step touches preferences/ranker/sources, then the target step file, then prior step files. Reference docs (01–04) override step files; the overview overrides everything.
