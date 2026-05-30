# Project Status

Single source of truth for "where are we right now?". Update this file at the end of every meaningful session.

## Snapshot (last updated: 2026-05-30, personal laptop)

| Step | State | Branch | Notes |
|---|---|---|---|
| 01 — Scaffolding | **Done, committed, pushed** | `step-01-scaffolding` (`1587dac`) | All 5 acceptance commands exit 0. |
| 02 — Database | **Done, committed, pushed** | `step-02-database` | Migration applied to Neon. All 5 acceptance commands exit 0. |
| 03 — Source registry | **Done, committed, pushed** | `step-02-database` (same branch) | 117 sources seeded. All acceptance commands pass. |
| 04–11 | Not started | — | — |

## What's on disk right now (this branch)

Everything from Steps 01 and 02, plus Step 03 deliverables:

- `migrations/0002_sources_unique.sql` — UNIQUE constraint on `sources(name, careers_url)`.
- `data/sources.yaml` — 117 sources across 8 categories. All careers URLs verified via httpx; 403s kept enabled (bot-blocked but live); 404s set enabled: false with notes.
- `src/policy_crawler/seed.py` — `load_yaml()`, `upsert_sources()`, CLI (`--apply` / `--validate-only`).
- `tests/test_seed.py` — YAML parse test + live upsert idempotency test.
- `pyproject.toml` — `requires-python` relaxed to `<3.14` (personal laptop has Python 3.13).

## Disabled sources (enabled: false)

17 sources have `enabled: false` because their careers_url returned 404 at seed time. Each has a note pointing to the organization's homepage. To enable, visit the homepage, find the current careers URL, update `data/sources.yaml`, and re-run the seed.

Notable disabled sources: Bruegel, CFR, IFRI, Kiel Institute, Wilson Center, SIPRI, RUSI, NATO, MERICS, Stanford E-IPER, TBI Fellowship.

## Next concrete actions (in order)

1. Decide: open PRs for steps 02 and 03, or proceed to Step 04.
2. Step 04 — Crawler framework: abstract fetcher base, RawJob type, ATS detection (greenhouse/lever/workday etc.), normalize pipeline.

## Conventions reminder

When kicking off any step, follow the agent preamble in [`docs/04-conventions.md`](04-conventions.md): read 00, 01, 03, 04 end-to-end, skim 02 if the step touches preferences/ranker/sources, then the target step file, then prior step files.
