# Step 07 — Vote Endpoint & Review Webapp

## Goal

Build the tiny FastAPI app that handles email vote-link clicks, establishes a session for deeper review, and serves the `/inbox`, `/sources`, and `/profile` pages. Deploy it to Vercel hobby tier.

## Reading list

- `docs/01-architecture.md` (§ "Vote endpoint + review webapp")
- `docs/03-tech-stack.md` (Vercel hobby; secrets list)
- `docs/04-conventions.md`
- `docs/steps/06-email-digest.md` (token format)

## Inputs / prereqs

- Steps 01–06 complete.
- A Vercel account; project linked to this GitHub repo (Vercel will auto-deploy on push to `main` once configured).
- Secrets present: `NEON_DATABASE_URL` (pooled), `TOKEN_HMAC_SECRET`, `SESSION_COOKIE_SECRET`, `DIGEST_FROM_EMAIL`, `DIGEST_TO_EMAIL`, `WEBAPP_BASE_URL`, `RESEND_API_KEY` (for "send me a magic link" reflow if a session expires).

## Deliverables

- `src/policy_crawler/webapp/main.py` — FastAPI app factory, dependency wiring, mounts the routes below.
- `src/policy_crawler/webapp/auth.py`:
  - `set_session(response, email)` — sets a signed cookie (HMAC; same secret as tokens, separate domain so the secret can be rotated independently).
  - `current_user(request) -> str | None`.
  - Dependency `require_session` that 401s if no valid cookie.
  - On 401, render a page that emails me a fresh magic link (Resend) — single-button form.
- `src/policy_crawler/webapp/routes/votes.py`:
  - `GET /v/{action}/{token}` where action ∈ `{up, down, save}`. Verifies token (kind = `vote`), atomically inserts a `feedback` row using a `consumed_tokens(token_nonce TEXT PRIMARY KEY)` table to enforce single-use, sets a session cookie tied to my email, renders a "thanks — vote recorded" page with a textarea POSTing back to `/v/feedback/{token}`.
  - `POST /v/feedback/{token}` — verifies token, updates the just-created feedback row's `freetext` field. Token re-use OK here (we keep a 30-min window after the original click).
- `src/policy_crawler/webapp/routes/inbox.py`:
  - `GET /inbox` — last 14 days of jobs, default sort by `pass2_score DESC`. Filters by posting type, geography, fit-score threshold, source category, and feedback state (unrated / upvoted / downvoted / saved). Server-rendered with Jinja2; no JS framework, no SPA — small HTMX touches OK.
  - `GET /inbox/{job_id}` — full description, all LLM fields, prior votes, free-text feedback form. Vote buttons here POST in the same shape the email links use (but JSON, with CSRF token via cookie).
- `src/policy_crawler/webapp/routes/sources.py`:
  - `GET /sources` — three tabs: "active", "suggested", "rejected". Each row in suggested has approve/reject/snooze buttons.
  - `POST /sources/suggested/{id}/approve|reject|snooze` — updates `suggested_sources`. On approve, also inserts into `sources` with `approved_by_me=true, enabled=true`.
  - `GET /sources/{id}/edit` — edit a single source's `fetcher_kind`, `fetcher_config`, `priority`, `geography_tags`, `enabled`. Useful for fixing selectors without redeploying.
- `src/policy_crawler/webapp/routes/profile.py`:
  - `GET /profile` — renders current `data/profile.yaml` (read from disk in dev; from a `profile_versions` table in production — see Implementation notes) and lists pending `proposed_profile_changes`.
  - `POST /profile/changes/{id}/approve|reject` — approves/rejects a proposed change. Approval applies the diff and writes the new profile to the next-version row in `profile_versions`. (In v1 it's fine if approval simply opens a PR via the GH PAT — see Step 10.)
- `src/policy_crawler/webapp/routes/status.py`:
  - `GET /status` — last run summaries, error counts, recent llm cost, table of source health (last_success_at vs last_checked_at). No auth required (no sensitive data; only counts and timestamps).
- `src/policy_crawler/webapp/routes/manual.py`:
  - `GET/POST /manual` — paste a job posting URL and a free-text description. Triggers a one-shot Sonnet extract (using the Pass 2 prompt minus the profile rendering — just structured extraction) into `jobs` with `source` set to the matching `sources` row of `fetcher_kind = 'manual'` (creating one named "Manual entry" if absent).
- Templates under `src/policy_crawler/webapp/templates/`. Use a single shared layout. Style: minimal CSS in one file, no JS framework. HTMX optional for the vote buttons.
- `vercel.json` at repo root configuring the Python runtime, the entrypoint (`src/policy_crawler/webapp/main.py:app`), and route rewrites so all paths funnel into the FastAPI app.
- A migration `migrations/0002_consumed_tokens_and_profile_versions.sql` for the new tables introduced here:
  - `consumed_tokens (nonce TEXT PRIMARY KEY, consumed_at TIMESTAMPTZ DEFAULT now())`.
  - `profile_versions (id UUID PRIMARY KEY, version INT, profile JSONB, created_at TIMESTAMPTZ, source TEXT)` — for tracking applied profile state separately from the YAML in git.
- `tests/webapp/test_*.py` — at minimum: token verify happy/sad path; `/v/up/{token}` records feedback; `/inbox` returns expected jobs; `/sources/suggested/{id}/approve` flow; CSRF protection on POSTs.

## Acceptance criteria

```bash
pytest -q tests/webapp/

# Local run:
uvicorn policy_crawler.webapp.main:app --reload --port 8000
# Visit http://localhost:8000/status — should render.

# Generate a fake token and visit:
python -c "from policy_crawler.digest.tokens import make_token; from datetime import timedelta; print(make_token({'job_id':'<some uuid>'}, kind='vote', expires_in=timedelta(days=14)))"
# Visit http://localhost:8000/v/up/<token> — confirms vote recorded; refresh same URL: now rejected (single-use).
```

After deploying to Vercel:

- `WEBAPP_BASE_URL/status` renders.
- A real digest email's vote links work end-to-end: click → confirmation → re-click → rejected.
- `/inbox` lists today's digested jobs.

## Implementation notes

- **Vercel Python runtime**: `vercel.json` `functions` map: `{"src/policy_crawler/webapp/main.py": {"runtime": "python3.12"}}` and `routes` rewriting `(.*)` to `/src/policy_crawler/webapp/main.py`. The `app` object is auto-detected by Vercel's Python runtime when exported via FastAPI.
- **Stateless function caveat**: don't initialize the connection pool at module import time. Use a lazy `get_pool()` cached at request scope. Cold starts otherwise time out before the first request.
- **Pooled DB URL**: required on Vercel. Direct URL would exhaust connections quickly.
- **Single-use tokens**: insert into `consumed_tokens` first; if `INSERT ... ON CONFLICT DO NOTHING` returns 0 rows, the token has already been used → render "already recorded" page (200 OK, not an error). Then insert into `feedback`.
- **CSRF**: standard double-submit cookie pattern for `POST /v/feedback/...` and other POSTs from the webapp pages.
- **Session cookie**: `HttpOnly`, `Secure` (in production), `SameSite=Lax`, signed with `SESSION_COOKIE_SECRET`. Contents: `{email, iat, exp}`. Expiry: 30 days. Renew on each request.
- **HTMX**: optional but nice for vote buttons; pulls in one ~12 KB script from a CDN. If used, document the CSP carefully.
- **Don't ship a public `/login`**. The only way in is a magic link, sent via Resend to `DIGEST_TO_EMAIL`. Rate-limit the magic-link issuer endpoint.
- **`/manual` LLM call**: keep it simple — fetch the URL with `httpx`, pass HTML + free-text to Sonnet with a one-shot extract tool, persist as a `Job` row tied to the "Manual entry" source.
- **Profile editing**: in v1, "approve a proposed change" can either (a) write directly to `profile.yaml` on disk + commit + push via a GH PAT, or (b) write to `profile_versions` and let the next daily run pick up the latest version. Option (a) gives a clear git audit trail; (b) is simpler. Step 10 picks one explicitly.

## Out of scope

- The orchestration cron (Step 08).
- Source discovery generation (Step 09).
- Profile self-update generation (Step 10) — this step only renders + accepts/rejects what Step 10 produces.
- Cost dashboards beyond a simple totals line (Step 11).

## Followups

- Replace the inline CSS with a tiny shared design tokens file.
- Add keyboard shortcuts on `/inbox` (`j`/`k`, `u`/`d`/`s`).
- Add an iOS Shortcuts integration once the webapp stabilizes.
