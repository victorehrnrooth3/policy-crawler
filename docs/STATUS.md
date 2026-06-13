# Project Status

Single source of truth for "where are we right now?". Update this file at the end of every meaningful session.

## Snapshot (last updated: 2026-06-13 — steps 09 + 10 built on step-09-source-config)

| Step | State | Branch | Notes |
|---|---|---|---|
| 01 — Scaffolding | **Done, merged to main** | `step-01-scaffolding` | All acceptance commands exit 0. |
| 02 — Database | **Done, merged to main** | — | Migration applied. Live DB tests pass. |
| 03 — Source registry | **Done, merged to main** | — | 117 sources seeded. |
| 04 — Crawler framework | **Done, merged to main** | — | ATS API fetchers + generic_html + manual. Idempotent on re-run. |
| 05 — Preference profile & ranker | **Done, merged to main** | — | Two-pass Haiku→Sonnet scoring live. |
| 06 — Email digest | **Done, merged to main** | — | tokens, compose, template, send via Resend. |
| 07 — Vote endpoint & webapp | **Done, merged to main** | — | FastAPI on Vercel. All routes smoke-tested. |
| 08 — Orchestration | **Done, merged to main** | — | CI workflow; `run.py` orchestrator. Connection-resilience fixes (keepalives + write retry). |
| 09 — Source config + discovery | **Done, PR open** | `step-09-source-config` | See detail below. |
| 10 — Preference self-update | **Done, PR open** | `step-09-source-config` | `self_update` package; weekly proposes a profile diff, `/profile` approve opens a PR via the GitHub API. See detail below. |
| 11 — Observability & guardrails | **Not started** | — | Foundation tables exist; no cost-cap logic or `/status` page yet. |

**244 tests passing**, 8 skipped (live-DB), 4 errored locally from a pre-existing `vcr`/`aiohttp` version mismatch (`aiohttp.streams.AsyncStreamReaderMixin`) that does not occur on a fresh CI install. `ruff` + `pyright` clean.

## What landed in step-09-source-config

This branch contains two phases of work: source configuration (wiring ATS APIs) and the new Camoufox Tier-2 fetcher + source discovery.

### Phase 1 — ATS source configuration

Built `crawler/detect.py` (ATS signature detection + direct API probing) and `crawler/rippling.py`. Result: **~22 sources now fetch via ATS JSON APIs** (was 2 at Step 04):

| ATS | Sources |
|---|---|
| Greenhouse (5) | Anthropic, Google DeepMind, Teneo, Human Rights Watch, Anduril (`title_keywords` filtered) |
| Lever (2) | Palantir, Commonwealth Fusion |
| Ashby (4) | Helion, Saronic, OpenAI (`title_keywords` filtered), Form Energy |
| Workable (1) | Control Risks |
| SmartRecruiters (1) | OECD |
| Rippling (1) | Eurasia Group |
| Workday (8) | RAND, TBI, Apollo, Equinor, Fed SF/Boston/Chicago (some `search_text`-scoped) |

### Phase 2 — Camoufox Tier-2 fetcher

Replaced the dead `playwright` / `rss` / `sitemap` / `generic_html` fetchers with a single **Camoufox** fetcher. Camoufox is a patched Firefox; its TLS fingerprint bypasses the iCIMS AWS WAF that blocked Playwright. Pipeline per source:

1. Render the careers URL with Camoufox, sleep `fetcher_config.wait_seconds` (default 6 s) to let JS boards hydrate.
2. Walk **all** `page.frames` — covers `#icims_content_iframe` generically, no site-specific code.
3. Call `claude-haiku-4-5-20251001` with a forced `extract_jobs` tool → `[{title, url, location}]`.
4. Log one `llm_calls` row per page (kind `crawl_extract`, ~$0.0085/page).

**50 think-tank / IGO / government / corporate sources** are now `fetcher_kind: camoufox` (previously `generic_html` with empty selectors — 0 jobs). iCIMS cluster (Brookings, Brookings RA, CFR) pointed at their `careers-*.icims.com` boards. ~24 PhD/fellowship rows disabled (no job-listing feed).

Smoke test: PIIE rendered and returned "Research Analyst: US Economic Statistics" locally. Brookings loaded fine (0 open positions at test time). CSIS disabled (Drupal CMS auth gate — URL needs investigation). Atlantic Council URL corrected to `/careers/`.

### Phase 2 — Weekly-only pipeline

Deleted `daily.yml`. Single **Sunday 07:30 UTC** cron runs everything:
```
crawl_all → score_pending → send_digest → run_discovery → run_self_update
```
All under `--kind weekly`. The `daily`, `weekly_discovery`, `weekly_self_update` kinds remain available for ad-hoc CLI / `workflow_dispatch` use. `weekly.yml` installs `.[camoufox]` and fetches the Firefox binary before running.

### Phase 2 — Source discovery

`src/policy_crawler/discovery/run.py`: Sonnet 4.6 proposes 10–20 employers → `detect_ats()` classifies each → known ATS gets its kind, everything else defaults to `camoufox` → queued in `suggested_sources` (status `pending`). Dedupes against live sources + pending queue. Human approval required; approved sources default to `camoufox` with no extra config.

### Phase 3 — Preference self-update (Step 10)

New `src/policy_crawler/self_update/` package:

- `summarize_feedback.py` — aggregates the last 7 days of `feedback` (joined to `jobs`) into a `FeedbackSummary`: vote tallies, liked/disliked jobs with free-text, posting-type mix, light geography token scan, and stopword-filtered free-text themes.
- `propose_diff.py` — one forced Sonnet 4.6 `propose_profile_diff` tool call returns a bounded **patch list** (≤ 10 add/remove/update ops, each with a `reason`). Retries once with a stricter system prompt if the model over-produces; zero ops is a valid no-op.
- `apply_diff.py` — JSON-Pointer-ish path engine (`must_haves[2]`, `topics.heavy[0].keywords[+]`, `geography.timeline_note`) over `ruamel.yaml` so comments/order survive. Guardrails: never touch `version`/`identity.cv_url`, never empty `must_haves`/`dealbreakers`; result is re-validated against the Pydantic `Profile`.
- `run.py` — `run_self_update(run_id)` proposes + dry-run-applies + queues a `proposed_profile_changes` row (status `pending`); never edits the profile. `apply_proposed(change_id, gh_pat)` (called by the webapp on approval) opens a PR via the **GitHub REST API** — chosen because the webapp runs on Vercel's read-only, repo-less filesystem.

Webapp `/profile`: approve now calls `apply_proposed` (opens the PR, marks the row `applied` only on success; a failed PR keeps the row pending and shows a 502). Reject marks `rejected`.

Migration 0004's `self_update` `llm_call_kind` was already present from `0001_init.sql`; no new migration needed for Step 10. New optional config `GITHUB_REPOSITORY` (default `victorehrnrooth3/policy-crawler`) names the PR target; set it as a Vercel env var so the approve route can open PRs.

### Migrations and DB state

Migration 0004 adds `camoufox`, `crawl_extract`, `weekly` enum values — **already applied to production Neon**. Step 10 added no migration (`self_update` `llm_call_kind` and `proposed_profile_changes` / `change_status` already shipped in `0001_init.sql`). New dependency: `ruamel.yaml~=0.18`.

Sources seeded: 78 enabled total.

| Fetcher | Count |
|---|---|
| `camoufox` | 50 |
| `workday_json` | 14 |
| `greenhouse` | 5 |
| `ashby` | 4 |
| `lever` | 2 |
| `rippling` | 1 |
| `workable` | 1 |
| `smartrecruiters` | 1 |

213 tests passing, 8 skipped (DB-live), `ruff` + `pyright` clean.

## Monthly cost estimate (steady state, weekly runs)

| Component | Estimate |
|---|---|
| Camoufox crawl (~50 pages/week × $0.0085) | ~$1.85/mo |
| Ranker pass 1 + pass 2 (~70 new jobs/week) | ~$2.00/mo |
| Source discovery (1 Sonnet call/week) | ~$0.20/mo |
| Preference self-update (≤ 1 Sonnet call/week) | ~$0.20/mo |
| **Total** | **~$4.25/mo** (target: <$5) |

## Pending checks on first weekly run

1. **CFR iCIMS subdomain** `careers-cfr` is an unverified guess — confirm from run logs.
2. **Atlantic Council** `/careers/` may still 403 in headless mode (Cloudflare) — check logs.
3. **Camoufox CI libs**: if the weekly workflow fails at browser launch on `ubuntu-24.04`, add the missing `apt-get install` step (Firefox deps).
4. **Camoufox driver crash containment** (fixed 2026-06-13): a first weekly dispatch crashed the whole run when the Playwright-Firefox driver hit `Cannot read properties of undefined (reading 'url')` (a malformed page `pageError`) and `process.exit`ed — bypassing Python's `try/except` and the failure-alert path. `camoufox_llm.py` now renders each source in a spawned child process (`render_candidates_isolated`, 120 s cap), so a driver crash/hang skips one source instead of aborting the run. Watch the next dispatch for `camoufox.render_failed` lines (expected, benign) rather than a hard process exit.
5. **Anduril greenhouse `title_keywords`** matched 0 of ~2085 roles on the last run (`crawl.title_filtered kept=0`) and the source has been silent since 2026-06-09 — revisit whether the keyword set is too narrow or Anduril simply has no open policy roles.

## Pending checks for Step 10 (first real self-update run)

1. **`GITHUB_REPOSITORY` on Vercel** — set it (and confirm `GH_PAT_FOR_PROFILE_PR` has `contents: write` + `pull_requests: write`) before approving a change, or the approve button returns 502.
2. **First PR shape** — after the first weekly run with real feedback, approve one change and eyeball the opened PR's `data/profile.yaml` diff to confirm comments/order are preserved.

## Next concrete actions

1. **Merge `step-09-source-config` → `main`** (CI must pass on the PR — it now also covers steps 09 and 10).
2. **Trigger a manual `workflow_dispatch` of `weekly.yml`** after merge to confirm the full pipeline (crawl → rank → digest → discovery → self-update) end-to-end.
3. **Start Step 11** — observability & guardrails: fold `crawl_extract` + `self_update` + `discovery` costs into `runs.total_cost_usd`, build the `/status` page, and wire the `RANKER_DEGRADE_TO_HAIKU_ONLY` cost-cap to real spend.

## Conventions reminder

When kicking off any step, follow the agent preamble in [`docs/04-conventions.md`](04-conventions.md): read 00, 01, 03, 04 end-to-end, skim 02 if the step touches preferences/ranker/sources, then the target step file.
