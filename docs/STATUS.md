# Project Status

Single source of truth for "where are we right now?". Update this file at the end of every meaningful session.

## Snapshot (last updated: 2026-05-31, personal laptop)

| Step | State | Branch | Notes |
|---|---|---|---|
| 01 — Scaffolding | **Done, merged to main** | `step-01-scaffolding` | All acceptance commands exit 0. |
| 02 — Database | **Done, merged to main** | — | Migration applied. Live DB tests pass. |
| 03 — Source registry | **Done, merged to main** | — | 117 sources seeded. |
| 04 — Crawler framework | **Done, pushed** | `step-04-crawler` | 591 jobs from Anthropic (Greenhouse) + Palantir (Lever). Idempotent on re-run. Post-audit fixes committed. |
| 05–11 | Not started | — | — |

## What's on disk right now (step-04-crawler branch)

Everything from Steps 01–03 (merged to main), plus:

- `src/policy_crawler/crawler/` — 11 fetchers, normalize, dedupe, run.py CLI.
- `tests/crawler/` — VCR cassettes + unit/DB tests.
- `data/sources.yaml` — 117 sources; Anthropic and Palantir have populated `fetcher_config`.
- **Post-audit fixes**: `run.py` uses parameterized queries (no string-formatted WHERE clauses); `_upsert_job` signature cleaned up.

## Live jobs in DB

After first crawl on 2026-05-31:
- **Anthropic** (Greenhouse, board=`anthropic`): ~371 roles fetched
- **Palantir** (Lever, company=`palantir`): ~220 roles fetched
- Total: 591 seen, 582 new (9 deduped cross-source). Second run: 0 new (idempotent).

## Sources needing `fetcher_config`

~115 sources are still `generic_html` with empty selectors. To configure more:
- Greenhouse: Add `{board: "<slug>"}` — slug usually = company name in lowercase
- Lever: Add `{company: "<slug>"}`
- Ashby: Add `{org: "<slug>"}`
- generic_html: Fill in `{selectors: {list_selector: ..., title_selector: ..., url_selector: ...}}`

## Next concrete actions (in order)

1. Start Step 05 — Preference profile & ranker: `data/profile.yaml`, `profile.py`, `pass1.py` (Haiku screen), `pass2.py` (Sonnet deep-score), schemas, prompts.
2. The ~582 jobs in the DB are ready to be scored.

## Conventions reminder

When kicking off any step, follow the agent preamble in [`docs/04-conventions.md`](04-conventions.md): read 00, 01, 03, 04 end-to-end, skim 02 if the step touches preferences/ranker/sources, then the target step file.
