# Project Status

Single source of truth for "where are we right now?". Update this file at the end of every meaningful session.

## Snapshot (last updated: 2026-06-07, personal laptop — step 08 complete)

| Step | State | Branch | Notes |
|---|---|---|---|
| 01 — Scaffolding | **Done, merged to main** | `step-01-scaffolding` | All acceptance commands exit 0. |
| 02 — Database | **Done, merged to main** | — | Migration applied. Live DB tests pass. |
| 03 — Source registry | **Done, merged to main** | — | 117 sources seeded. |
| 04 — Crawler framework | **Done, merged to main** | — | 591 jobs from Anthropic (Greenhouse) + Palantir (Lever). Idempotent on re-run. Post-audit fixes committed. |
| 05 — Preference profile & ranker | **Done, merged to main** | — | Live scoring confirmed working. |
| 06 — Email digest | **Done, merged to main** | — | tokens, compose, template, send. |
| 07 — Vote endpoint & webapp | **Done, merged to main** | — | FastAPI app deployed on Vercel. All routes smoke-tested. |
| 08 — Orchestration | **Code complete** | `step-08-orchestration` | CI/daily/weekly workflows; `run.py` orchestrator; `obs/runs.py` helpers; 7 new tests. Needs GitHub Actions secrets wired up before first scheduled run. |
| 09–11 | Not started | — | — |

## What's on disk right now (step-08-orchestration branch)

Everything from Steps 01–07 (merged to main), plus:

- `.github/workflows/ci.yml` — ruff + pyright + pytest on PR/push-to-main.
- `.github/workflows/daily.yml` — cron `15 6 * * *`; runs `python -m policy_crawler.run --kind daily`.
- `.github/workflows/weekly.yml` — cron `30 7 * * 0`; runs discovery + self-update sequentially.
- `src/policy_crawler/run.py` — top-level orchestrator CLI (dispatches by `--kind`).
- `src/policy_crawler/obs/runs.py` — `start_run()` / `finish_run()` shared helpers.
- `src/policy_crawler/config.py` — added `RANKER_DEGRADE_TO_HAIKU_ONLY` kill-switch flag.
- `src/policy_crawler/crawler/run.py` — `crawl_all()` accepts optional `run_id` param.
- `src/policy_crawler/ranker/run.py` — pass-2 skipped when `RANKER_DEGRADE_TO_HAIKU_ONLY=true`.
- `tests/test_run_wrapper.py` — 7 tests; all passing.
- 176 tests total, 8 skipped (DB-live tests without NEON_DATABASE_URL).

## Live jobs in DB

After first crawl on 2026-05-31:
- **Anthropic** (Greenhouse, board=`anthropic`): ~371 roles fetched
- **Palantir** (Lever, company=`palantir`): ~220 roles fetched
- Total: 591 seen, 582 new (9 deduped cross-source). Second run: 0 new (idempotent).
- **pass1_score**: all NULL (not yet scored — waiting for API key)

## To run first scoring batch

```bash
# 1. Populate .env with ANTHROPIC_API_KEY
# 2. Run Pass 1 + Pass 2 on 20 jobs:
python -m policy_crawler.ranker.run --limit 20

# 3. Verify results:
# SELECT count(*) FILTER (WHERE pass1_score IS NOT NULL) AS p1,
#        count(*) FILTER (WHERE pass2_score IS NOT NULL) AS p2
# FROM jobs;
```

## Sources needing `fetcher_config`

~115 sources are still `generic_html` with empty selectors. To configure more:
- Greenhouse: Add `{board: "<slug>"}` — slug usually = company name in lowercase
- Lever: Add `{company: "<slug>"}`
- Ashby: Add `{org: "<slug>"}`
- generic_html: Fill in `{selectors: {list_selector: ..., title_selector: ..., url_selector: ...}}`

## Next concrete actions (in order)

1. **Wire GitHub Actions secrets** — go to repo Settings → Secrets and variables → Actions and add:
   `ANTHROPIC_API_KEY`, `NEON_DATABASE_URL`, `RESEND_API_KEY`, `DIGEST_FROM_EMAIL`,
   `DIGEST_TO_EMAIL`, `WEBAPP_BASE_URL`, `TOKEN_HMAC_SECRET`. Optionally `GH_PAT_FOR_PROFILE_PR`.
2. Merge `step-08-orchestration` → `main`. CI workflow will run automatically on the PR.
3. Trigger a manual `workflow_dispatch` of `daily.yml` from the GitHub Actions UI to confirm end-to-end success.
4. Start Step 09 — Source discovery (weekly job).

## Conventions reminder

When kicking off any step, follow the agent preamble in [`docs/04-conventions.md`](04-conventions.md): read 00, 01, 03, 04 end-to-end, skim 02 if the step touches preferences/ranker/sources, then the target step file.
