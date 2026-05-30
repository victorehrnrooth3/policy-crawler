# policy-crawler

A small, mostly-deterministic system that crawls a curated list of employer pages once a day, scores postings against my preference profile with Claude, and emails me a digest with one-click vote links. Feedback feeds back into source discovery and preference updates — both human-in-the-loop.

**Status:** documentation phase. No application code yet — this repo currently contains the full execution roadmap that an AI coding agent will follow step-by-step to build the system.

## Where to start

Read the docs in this order:

1. [`docs/00-overview.md`](docs/00-overview.md) — what this is, why, success criteria, full step roadmap.
2. [`docs/01-architecture.md`](docs/01-architecture.md) — components, data flow, data model, fetcher tiers, ranker design.
3. [`docs/02-personal-context.md`](docs/02-personal-context.md) — CV, career thesis, topic + geography preferences, exemplar liked/disliked roles.
4. [`docs/03-tech-stack.md`](docs/03-tech-stack.md) — locked tech choices and the full secrets list.
5. [`docs/04-conventions.md`](docs/04-conventions.md) — code style, testing, commit, and **agent-prompting conventions**.

Then walk the steps in order:

| # | Step | Doc |
|---|------|-----|
| 01 | Scaffolding | [`docs/steps/01-scaffolding.md`](docs/steps/01-scaffolding.md) |
| 02 | Database | [`docs/steps/02-database.md`](docs/steps/02-database.md) |
| 03 | Source registry & seed | [`docs/steps/03-source-registry.md`](docs/steps/03-source-registry.md) |
| 04 | Crawler framework | [`docs/steps/04-crawler-framework.md`](docs/steps/04-crawler-framework.md) |
| 05 | Preference profile & ranker | [`docs/steps/05-preference-and-ranker.md`](docs/steps/05-preference-and-ranker.md) |
| 06 | Email digest | [`docs/steps/06-email-digest.md`](docs/steps/06-email-digest.md) |
| 07 | Vote endpoint & review webapp | [`docs/steps/07-vote-endpoint-and-webapp.md`](docs/steps/07-vote-endpoint-and-webapp.md) |
| 08 | GitHub Actions orchestration | [`docs/steps/08-orchestration.md`](docs/steps/08-orchestration.md) |
| 09 | Source discovery | [`docs/steps/09-source-discovery.md`](docs/steps/09-source-discovery.md) |
| 10 | Preference self-update | [`docs/steps/10-preference-self-update.md`](docs/steps/10-preference-self-update.md) |
| 11 | Observability & cost guardrails | [`docs/steps/11-observability-and-guardrails.md`](docs/steps/11-observability-and-guardrails.md) |

## Working with these docs (for an AI agent)

When I ask you to execute Step N:

1. Read `docs/00-overview.md`, `docs/01-architecture.md`, `docs/03-tech-stack.md`, and `docs/04-conventions.md` end-to-end.
2. Skim `docs/02-personal-context.md` if the step touches preferences/ranker/sources.
3. Read `docs/steps/NN-*.md` end-to-end.
4. Skim every prior step file (`01..N-1`) so you know what already exists.
5. Build only what the step's "Deliverables" section calls for; verify "Acceptance criteria" before declaring done.
6. If docs contradict each other, stop and ask. Reference docs (01–04) override step files; the overview overrides everything.

## Stack at a glance

Python 3.12 · Neon Postgres · Anthropic Claude (Haiku 4.5 → Sonnet 4.6) · Resend · FastAPI · Vercel hobby · GitHub Actions cron. All free tier or near-free for a single user. Full rationale in [`docs/03-tech-stack.md`](docs/03-tech-stack.md).

## Install & test

Requires Python 3.12. From a clean clone:

```bash
python -m venv .venv
. .venv/Scripts/activate            # PowerShell: .venv\Scripts\Activate.ps1
                                    # bash/zsh:   source .venv/bin/activate
pip install -e .[dev]

ruff check .
ruff format --check .
pyright
pytest -q
```

All five commands should exit 0 on a fresh checkout. See [`docs/steps/01-scaffolding.md`](docs/steps/01-scaffolding.md) for the canonical acceptance criteria.

## Database setup

1. Create a free-tier Neon project named `policy-crawler` at neon.tech.
2. Copy the **pooled** connection string (host contains `-pooler.`) into `.env` as `NEON_DATABASE_URL`, and the **direct** one as `NEON_DATABASE_URL_DIRECT`.
3. Apply the schema:

   ```
   python migrations/_apply.py
   ```

   Expect: "Applied 0001_init.sql" then "All migrations up to date."

4. Verify in Neon's SQL editor that all 8 tables and 12 enums exist.

Re-running `python migrations/_apply.py` is a no-op.
