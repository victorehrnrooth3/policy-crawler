# Policy Crawler + Ranker — Project Overview

## What this is

A small, mostly-deterministic system that:

1. Crawls a curated list of employer/source websites once a day.
2. Normalizes and deduplicates job postings, fellowships, predocs, and PhD program calls.
3. Asks Claude to score each new posting against a **preference profile** seeded from my CV and career thesis.
4. Sends me a short email digest each morning with the top matches and one-click vote links.
5. Learns from my votes and free-text feedback over time, surfacing **proposed** changes to the preference profile and **proposed** new sources to monitor — never auto-applying either.

The system is intentionally not an autonomous browsing agent. The crawler is normal, auditable software. The LLM is used only for judgment (ranking, explanation, summarization, source suggestion).

## Why I'm building this

I'm exploring a relatively wide career space — top US PhDs (econ, public policy, sustainable development, IO/applied micro), think tanks (especially energy / defense / geopolitics / tech-AI), asset-manager policy institutes (BlackRock BII, KKR Global Institute), geopolitical-risk firms (Eurasia, Rhodium, MAP), corporate policy at frontier-tech / defense / energy companies (Anthropic, OpenAI, Anduril, Palantir, NextEra), and IGOs / YPPs (OECD, IEA, World Bank, IMF, EU EPSO). The number of plausible employers is too high to monitor by hand, and the postings too heterogeneous (full roles vs fellowships vs predocs vs program calls).

I'd rather spend my judgment on which 5 jobs to engage with each week than on which 50 careers pages to refresh.

## Goals

- **Daily, not real-time.** One run per day is enough.
- **Cheap, ideally free.** GitHub Actions cron + Neon Postgres free tier + Anthropic API + Resend free tier + Vercel hobby. No always-on servers.
- **Mostly hands-off.** Email is the daily driver. I read 6–10 cards on my phone, vote, optionally type a sentence of feedback. Deeper review is on a private webapp run when I want it.
- **Transparent and auditable.** Every fetch, every LLM call, every score is logged. I can always answer "why did the system recommend this?" and "what changed in my profile?"
- **Human-in-the-loop on changes.** New sources never get auto-added. Preference profile updates are surfaced as a diff and require my approval.
- **Easy for an AI agent to extend.** Each step in `docs/steps/` is sized so a coding agent can finish it in roughly one focused session.

## Non-goals

- Not a general agent that browses sites freely. Crawling is deterministic.
- Not a public service. One user (me). No multi-tenant concerns.
- Not a scoring leaderboard. The ranker is a tool to surface candidates; the decision is mine.
- Not a CRM / ATS / outreach tool. Application logistics are out of scope. Possible future addition.
- Not a job-aggregator clone (LinkedIn, Indeed). I deliberately avoid those — signal-to-noise is too low and they don't index policy-shop pages well anyway.

## Success criteria (12-week look-back)

- I am opening the daily email at least 4 days a week.
- I have voted (up/down/save) on ≥ 80% of cards delivered.
- The system has surfaced at least 3 employers I'd want to monitor that I had not previously identified.
- The preference profile has been updated at least twice from feedback diffs I approved.
- Total monthly cost: < $5 in Anthropic spend, $0 in hosting.

## How the documentation is organized

Each file has a job. Read this one first; everything else is reference or step-specific.

- **`00-overview.md`** (this file) — what we're building, why, and how the docs fit together.
- **`01-architecture.md`** — durable architecture reference: components, data flow, data model, fetcher tiers, ranker design, posting-type taxonomy. Read once and skim before any step.
- **`02-personal-context.md`** — durable personal reference: my CV, career thesis, topic/geography preferences, and exemplar liked/disliked roles. The preference profile in Step 5 is bootstrapped from this. Update this file as my situation evolves.
- **`03-tech-stack.md`** — locked tech choices, rationale per choice, full secrets list.
- **`04-conventions.md`** — code style, testing, commit conventions, and **agent-prompting conventions** — the standard preamble to give an agent before kicking off a step.
- **`steps/NN-*.md`** — one file per implementation step. Each has Goal / Reading list / Inputs / Deliverables / Acceptance criteria / Implementation notes / Out of scope.

## Step roadmap

| # | Step | Done when |
|---|------|-----------|
| 01 | Scaffolding | `pip install -e .[dev]`, `pytest`, and `ruff` all pass on an empty repo. |
| 02 | Database | Migrations apply against Neon URL; smoke insert/select round-trips. |
| 03 | Source registry & seed | `data/sources.yaml` loads idempotently; ~80 categorized, geo-tagged sources in DB. |
| 04 | Crawler framework | Tiered fetchers run end-to-end against seed; jobs table populated and idempotent. |
| 05 | Preference profile & ranker | Two-pass Haiku→Sonnet scoring produces ranked output with reasons; under cost cap. |
| 06 | Email digest | `python -m policy_crawler.digest --send-to ME` lands in my inbox with working vote links. |
| 07 | Vote endpoint & review webapp | Vercel deployment accepts vote-link clicks; `/inbox`, `/sources`, `/profile` work. |
| 08 | GitHub Actions orchestration | Daily and weekly workflows succeed on cron and `workflow_dispatch`; logs persisted. |
| 09 | Source discovery | Weekly run produces ≥10 candidate employers with rationales; approval flow wired. |
| 10 | Preference self-update | Weekly run proposes a structured diff to `profile.yaml` with per-change rationale. |
| 11 | Observability & cost guardrails | Per-run cost report; soft cap degrades to Haiku-only; failure email alert works. |

## How to use these docs (instructions for an AI agent)

When I ask you to execute Step N, do this in order:

1. Read this file (`00-overview.md`) end-to-end.
2. Read `01-architecture.md`, `03-tech-stack.md`, and `04-conventions.md` end-to-end. They are short on purpose.
3. Skim `02-personal-context.md` only if Step N involves the preference profile, the ranker, or source seeding.
4. Read the target step file (`steps/NN-*.md`) end-to-end.
5. Read every step file numbered **less than N** (skim is fine) so you know what already exists. Do not assume earlier steps were skipped.
6. Build only what the step's "Deliverables" section calls for. Resist scope creep — anything tempting that isn't listed goes in a `## Followups` section at the end of the step file as a comment.
7. Verify the step's "Acceptance criteria" before declaring done.
8. If you encounter a contradiction between docs, **stop and ask**. The reference docs (`01`–`04`) override the step files in case of conflict; this overview overrides everything.

## Departures from the original GPT proposal

For context if you're curious why some choices look different from what GPT initially suggested:

- **Streamlit Community Cloud is rejected.** It's public-by-default and my CV + feedback are personal. Replaced with a private Vercel-hosted FastAPI app behind signed-token URLs.
- **ATS coverage is broader than Greenhouse / Lever / Ashby.** Think tanks, asset-manager institutes, and IGOs mostly use Workday, iCIMS, custom HTML, RSS, or have no API at all. The fetcher framework is tiered to handle that reality.
- **Source discovery is in v1, not v3.** Given how broad my career exploration is right now, finding *new* employers to monitor is at least as valuable as ranking jobs at known ones.
- **Posting type is a first-class field.** Predocs (RFF, Brookings RA, CSET), fellowships (Knight-Hennessy, Schwarzman), PhD program calls, and YPPs (OECD, World Bank, IMF) all flow through the same pipeline as regular jobs.
- **Geography is a first-class field.** I'm in London now, US (Bay Area / Boston / NYC / Chicago) ~12 months out. The ranker uses this and updates over time.
