# Project Status

Single source of truth for "where are we right now?". Update this file at the end of every meaningful session.

## Snapshot (last updated: 2026-06-13 — step-09-source-config PR open, pending merge)

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
| 09 — Source config + discovery | **Done, PR open** | `step-09-source-config` | See detail below. 213 tests, ruff+pyright clean. |
| 10 — Preference self-update | **Not started** | — | Stub wired in `run.py`. Next step. |
| 11 — Observability & guardrails | **Not started** | — | Foundation tables exist; no cost-cap logic or `/status` page yet. |

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
crawl_all → score_pending → send_digest → run_discovery → _run_weekly_self_update (stub)
```
All under `--kind weekly`. The `daily`, `weekly_discovery`, `weekly_self_update` kinds remain available for ad-hoc CLI / `workflow_dispatch` use. `weekly.yml` installs `.[camoufox]` and fetches the Firefox binary before running.

### Phase 2 — Source discovery

`src/policy_crawler/discovery/run.py`: Sonnet 4.6 proposes 10–20 employers → `detect_ats()` classifies each → known ATS gets its kind, everything else defaults to `camoufox` → queued in `suggested_sources` (status `pending`). Dedupes against live sources + pending queue. Human approval required; approved sources default to `camoufox` with no extra config.

### Migrations and DB state

Migration 0004 adds `camoufox`, `crawl_extract`, `weekly` enum values — **already applied to production Neon**.

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
| **Total** | **~$4.05/mo** (target: <$5) |

## Pending checks on first weekly run

1. **CFR iCIMS subdomain** `careers-cfr` is an unverified guess — confirm from run logs.
2. **Atlantic Council** `/careers/` may still 403 in headless mode (Cloudflare) — check logs.
3. **Camoufox CI libs**: if the weekly workflow fails at browser launch on `ubuntu-24.04`, add the missing `apt-get install` step (Firefox deps).

## Next concrete actions

1. **Merge `step-09-source-config` → `main`** (CI must pass on the PR).
2. **Trigger a manual `workflow_dispatch` of `weekly.yml`** after merge to confirm end-to-end on the new architecture.
3. **Start Step 10** — preference self-update. The stub in `run.py` is already wired.

## Conventions reminder

When kicking off any step, follow the agent preamble in [`docs/04-conventions.md`](04-conventions.md): read 00, 01, 03, 04 end-to-end, skim 02 if the step touches preferences/ranker/sources, then the target step file.
