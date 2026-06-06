# Project Status

Single source of truth for "where are we right now?". Update this file at the end of every meaningful session.

## Snapshot (last updated: 2026-06-06, personal laptop)

| Step | State | Branch | Notes |
|---|---|---|---|
| 01 — Scaffolding | **Done, merged to main** | `step-01-scaffolding` | All acceptance commands exit 0. |
| 02 — Database | **Done, merged to main** | — | Migration applied. Live DB tests pass. |
| 03 — Source registry | **Done, merged to main** | — | 117 sources seeded. |
| 04 — Crawler framework | **Done, merged to main** | — | 591 jobs from Anthropic (Greenhouse) + Palantir (Lever). Idempotent on re-run. Post-audit fixes committed. |
| 05 — Preference profile & ranker | **Code complete, live scoring confirmed working** | `step-05-ranker` | Live scoring ran successfully. Palantir jobs score low (5–25) and skip — not a real target. Awaiting merge to main. |
| 06 — Email digest | **Code complete** | `step-06-email-digest` | tokens, compose, template, send, 33 tests passing. Needs Resend API key + verified domain to send real email. |
| 07–11 | Not started | — | — |

## What's on disk right now (step-06-email-digest branch)

Everything from Steps 01–04 (merged to main), plus:

- `data/profile.yaml` — full preference profile (identity, topics, geography, dealbreakers, exemplars).
- `src/policy_crawler/ranker/` — profile.py, schemas.py, prompts.py, pass1.py (Haiku), pass2.py (Sonnet), run.py (orchestrator + CLI).
- `tests/ranker/` — 56 tests, all passing (1 skipped without DB).
- `src/policy_crawler/digest/` — tokens.py, compose.py, template.py, send.py, __main__.py + Jinja2 templates.
- `tests/digest/` — 33 tests, all passing (1 skipped without DB).
- Ruff + pyright clean (0 errors).

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

1. Populate remaining `.env` secrets: `RESEND_API_KEY`, `DIGEST_FROM_EMAIL`, `DIGEST_TO_EMAIL`, `WEBAPP_BASE_URL`, `TOKEN_HMAC_SECRET`.
2. Dry-run the digest: `python -m policy_crawler.digest --dry-run` → opens `out/digest-YYYY-MM-DD.html`.
3. Send a real email: `python -m policy_crawler.digest --send` → confirm receipt.
4. Merge `step-05-ranker` to main, then merge `step-06-email-digest` to main.
5. Start Step 07 — Vote endpoint + webapp.

## Conventions reminder

When kicking off any step, follow the agent preamble in [`docs/04-conventions.md`](04-conventions.md): read 00, 01, 03, 04 end-to-end, skim 02 if the step touches preferences/ranker/sources, then the target step file.
