# Project Status

Single source of truth for "where are we right now?". Update this file at the end of every meaningful session.

## Snapshot (last updated: 2026-05-30, personal laptop)

| Step | State | Branch | Notes |
|---|---|---|---|
| 01 — Scaffolding | **Done, merged to main** | `step-01-scaffolding` (`1587dac`) | All acceptance commands exit 0. |
| 02 — Database | **Done, merged to main** | — | Migration applied. Live DB tests pass. |
| 03 — Source registry | **Done, merged to main** | — | 117 sources seeded. |
| 04 — Crawler framework | **Done, in progress** | `step-04-crawler` (this branch) | Framework complete. Sources need `fetcher_config` populated before crawl yields jobs. See below. |
| 05–11 | Not started | — | — |

## What's on disk right now (this branch)

Everything from Steps 01–03 merged to main, plus Step 04:

- `src/policy_crawler/crawler/` — base, registry, 11 fetchers, normalize, dedupe, run.py.
- `tests/crawler/` — VCR tests for Greenhouse (anthropic board), Lever (palantir), Ashby (ashby); normalize/dedupe unit tests; DB integration tests for upsert/idempotency/versioning.
- `tests/cassettes/` — recorded VCR cassettes.
- `pyproject.toml` — added `feedparser~=6.0` and `markdownify~=0.13`.

## Active note: source configuration needed

The crawl runs successfully (status=succeeded, 0 errors) but yields 0 jobs because:
- All `generic_html` sources have `fetcher_config: {}` (no selectors set yet). Use `python -m policy_crawler.crawler.run --configure-generic-html` to see which sources need selectors.
- `greenhouse`/`lever`/`ashby` sources in the DB have `fetcher_kind: generic_html` + empty config. To get jobs, update `fetcher_config` in `data/sources.yaml` with the correct board/company/org slug, then re-seed.
- `workday_json` sources need the careers URL to redirect to a `myworkdayjobs.com` URL, or explicit `fetcher_config.endpoint`.

**Confirmed working board slugs** (for Step 03 YAML updates):
- Greenhouse: `anthropic` (371 jobs), `stripe` (474 jobs)
- Lever: `palantir` (works)
- Ashby: `ashby` (57 jobs)

## Next concrete actions (in order)

1. Populate `fetcher_config` for a handful of known Greenhouse/Lever/Ashby sources in `data/sources.yaml` and re-seed, so the crawl yields real jobs.
2. Proceed to Step 05 (preference profile & ranker).

## Conventions reminder

When kicking off any step, follow the agent preamble in [`docs/04-conventions.md`](04-conventions.md): read 00, 01, 03, 04 end-to-end, skim 02 if the step touches preferences/ranker/sources, then the target step file, then prior step files.
