# Tech Stack & Secrets

Locked technology choices. Each step file references this rather than re-deciding. If a future agent thinks one of these is wrong, **stop and ask** rather than swapping a stack mid-build.

## Stack at a glance

| Concern | Choice | Why |
|---|---|---|
| Language | **Python 3.12** | Best library coverage for HTML parsing + ML/LLM tooling. I know enough Python; second stack would create friction. |
| Package & deps | **`pyproject.toml`** with `[project]` + `[project.optional-dependencies]`, `uv` or `pip` for install | Modern, no `requirements.txt` sprawl. |
| Linter / formatter | **`ruff`** (lint + format) | Fast, replaces black + isort + flake8. |
| Type checks | **`pyright`** in non-strict mode | Lightweight; catches the common errors. |
| Tests | **`pytest`** + **`pytest-vcr`** for HTTP fixtures | Standard. VCR cassettes keep fetcher tests deterministic. |
| HTTP client | **`httpx`** (sync, with retries) | Modern requests-replacement, ergonomic. |
| HTML parsing | **`selectolax`** (lexbor backend) | Much faster than BeautifulSoup; CSS-selector ergonomics. |
| Browser automation | **`camoufox`** (patched Firefox) for the Tier-3 long-tail fetcher | Replaces Playwright; different TLS fingerprint bypasses iCIMS AWS WAF. Lazy-imported so CI/dev installs don't require the browser binary. Install with `pip install -e ".[camoufox]" && python -m camoufox fetch`. |
| Data validation | **`pydantic` v2** | Job/Source models, ranker structured output. |
| LLM SDK | **`anthropic`** (official Python SDK) | Tool-use for structured output; cheap on Haiku, capable on Sonnet. |
| Database | **Neon Postgres** (free tier, scale-to-zero) | Postgres without server overhead. Free tier: 100 CU-hours / project, 0.5 GB / project. |
| DB driver | **`psycopg`** v3 (sync + async) | Modern psycopg, no SQLAlchemy unless we feel pain. |
| Migrations | Plain SQL files in `migrations/`, applied with a small Python runner | Avoid Alembic complexity for a single-user project. |
| Email | **Resend** (free tier: 100 emails/day, 3 000 / month) | Best DX for transactional email; free tier comfortably covers a daily digest. |
| Web framework | **FastAPI** + **Jinja2** templates | Tiny app; FastAPI integrates cleanly with the Vercel Python runtime. |
| Web hosting | **Vercel hobby tier** (free), Python serverless runtime | Free, low-cold-start, fits "tiny FastAPI app + a couple of pages." |
| Scheduler | **GitHub Actions cron** | Free for public repos; generous free minutes for private. **Single weekly schedule** (Sunday 07:30 UTC). No daily cron. |
| Secrets in CI | **GitHub Actions secrets** | Standard. |
| Secrets in webapp | **Vercel project env vars** | Encrypted at rest, scoped to project. |
| Local dev secrets | **`.env`** loaded via `python-dotenv`; **never committed** | `.env.example` in the repo as a template. |
| Observability | Postgres `runs` + `llm_calls` tables; `/status` HTML page; failure email via Resend | Lightweight, single-user observability. No Datadog. |

## Locked LLM choices

- **Pass 1 (screen)**: `claude-haiku-4-5` (or successor in same tier). Cheap, fast.
- **Pass 2 (deep score)**: `claude-sonnet-4-6` (or successor in same tier). Reasoning-quality matters for borderline cases.
- **Source discovery + preference self-update**: `claude-sonnet-4-6`. These are weekly so cost is negligible, and they benefit from stronger reasoning.

Always use Anthropic **tool use** for structured output. Never parse free-form JSON out of a text response.

## Why each major choice

### Why Neon and not SQLite or Cloudflare D1

- SQLite-on-CI: state would not persist across runs. Eliminated.
- Cloudflare D1: nice if we were TypeScript-end-to-end, but mixing Python crawler with a TS-only DB driver story is friction.
- Neon: managed Postgres with scale-to-zero, generous free tier, plays well with both GitHub Actions and Vercel. Connection pooler URL handles the serverless connection-limit gotcha.

### Why GitHub Actions and not Cloudflare Workers / Vercel cron / a hosted scheduler

- GitHub Actions runs Python natively, has 6-hour timeout headroom, and has a clean `workflow_dispatch` for ad-hoc runs.
- Cloudflare Workers cron is great but JS-only; would force a TS rewrite of the crawler.
- Vercel cron exists but the function timeout (10–60 sec on hobby) is tight for a full crawl + score pipeline.
- GitHub Actions also gives us Git-history-as-an-artifact for `profile.yaml` self-update commits.

### Why Vercel hobby and not a Python container on Render / Fly

- Single, low-traffic FastAPI app handling vote-link clicks + a small dashboard. Vercel's Python runtime is stateless, free, and has the right cold-start profile.
- Render free tier sleeps after inactivity (cold-start delay of ~30s on a vote click is poor UX from email).
- Fly.io free tier is workable but more setup.

### Why Resend and not SendGrid / SES / SMTP

- Resend's API is the most pleasant to write against, the free tier is sufficient, and DKIM setup is straightforward.
- SES is cheaper at scale but more setup overhead and we are not at scale.

## Secrets list

Every secret used by the system, where it lives, and what touches it.

| Secret | Where it lives | Used by |
|---|---|---|
| `ANTHROPIC_API_KEY` | GitHub Actions secret + Vercel env var (only if the webapp ever calls the LLM directly; v1 it doesn't) | Crawler/ranker job, weekly jobs. |
| `NEON_DATABASE_URL` (with pooler) | GitHub Actions secret + Vercel env var | All DB access. Pooler variant on Vercel; direct variant for migrations from local. |
| `NEON_DATABASE_URL_DIRECT` | Local `.env` only | Migration runs from a developer machine. |
| `RESEND_API_KEY` | GitHub Actions secret | Email digest job + failure-alert email. |
| `DIGEST_FROM_EMAIL` | GitHub Actions secret + Vercel env var | Sender address (e.g., `digest@policycrawler.dev` once a domain is set up). |
| `DIGEST_TO_EMAIL` | GitHub Actions secret + Vercel env var | My personal address. |
| `WEBAPP_BASE_URL` | GitHub Actions secret + Vercel env var | Used to build vote-link URLs in emails. |
| `TOKEN_HMAC_SECRET` | GitHub Actions secret + Vercel env var | HMAC key for signed magic-link / vote tokens. ≥ 32 random bytes. |
| `SESSION_COOKIE_SECRET` | Vercel env var | Cookie signing for webapp sessions. |
| `GH_PAT_FOR_PROFILE_PR` (optional, only used by self-update) | GitHub Actions secret | A fine-grained PAT scoped to this repo, used by the weekly self-update job to open a PR with the proposed `profile.yaml` change. |

`.env.example` (committed) lists all of the above with placeholder values. `.env` (gitignored) is the local mirror.

## Versioning policy

- Pin Python in `pyproject.toml` (`requires-python = ">=3.12,<3.13"`).
- Pin top-level dependencies to compatible-release ranges (`~=`) in `pyproject.toml`.
- The Anthropic SDK is unpinned beyond major (we want bug fixes and new model support); pin in `pyproject.toml` if a regression appears.
- Migrations are append-only and ordered by filename (`0001_init.sql`, `0002_…`). Never edit a migration after it ships.

## What is explicitly NOT in this stack (and why)

- **Streamlit / Streamlit Community Cloud** — public-by-default; rejected for personal-data privacy.
- **LangChain / LlamaIndex / agent frameworks** — needless abstraction over a small set of well-defined LLM calls. Use the Anthropic SDK directly.
- **SQLAlchemy / ORMs** — overkill for this schema size; raw SQL via `psycopg` is clearer.
- **Celery / Redis / message queues** — there's no async work that needs a queue; GitHub Actions is the queue.
- **Datadog / Sentry / OpenTelemetry** — overkill at single-user scale; the `runs` + `llm_calls` tables plus a `/status` page are enough.
- **Authentication providers (Auth0, Clerk, Supabase Auth)** — overkill; signed-token magic links suffice for one user.
- **Docker** — GitHub Actions and Vercel both build from source; a Dockerfile would be redundant.

## When to revisit choices

- If Anthropic's pricing materially shifts or a Gemini/OpenAI model becomes obviously cheaper-per-quality for the screen pass, revisit Pass 1 only.
- If Vercel hobby ever pushes Python to a paid tier, the webapp moves to Render or Fly.
- If Neon pricing/limits tighten, Supabase free tier is the next candidate.
- If we add any second user, all of this needs revisiting (auth especially).
