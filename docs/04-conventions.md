# Conventions

Code, testing, commit, and agent-prompting conventions. Short on purpose.

## Project layout

```
policy-crawler/
  pyproject.toml
  ruff.toml                 # or [tool.ruff] in pyproject
  .env.example
  .gitignore
  README.md
  docs/                     # all roadmap docs (this folder)
  data/
    sources.yaml            # hand-curated sources seed
    profile.yaml            # current preference profile
  migrations/
    0001_init.sql
    0002_*.sql
  src/policy_crawler/
    __init__.py
    config.py               # env loading, settings model
    db.py                   # connection helpers
    models.py               # pydantic shared types
    crawler/
      __init__.py
      base.py               # Fetcher abstract base + RawJob type
      registry.py           # fetcher_kind -> Fetcher map
      detect.py             # ATS signature detection (URL patterns + direct API probing)
      greenhouse.py
      lever.py
      ashby.py
      workable.py
      smartrecruiters.py
      rippling.py
      workday.py
      camoufox_llm.py       # Tier-3 long-tail: Camoufox render + Haiku extract
      generic_html.py       # Retained (enum value); 0 enabled sources
      manual.py
      normalize.py          # RawJob -> Job
      dedupe.py
    ranker/
      __init__.py
      schemas.py            # tool-use schemas
      profile.py            # profile.yaml load + validate
      pass1.py              # Haiku screen
      pass2.py              # Sonnet deep score
      prompts.py            # prompt templates
    digest/
      __init__.py
      compose.py            # pick top-K
      template.py           # HTML + plaintext
      send.py               # Resend client
      tokens.py             # HMAC signing for vote links
    discovery/
      __init__.py
      run.py                # Unified: summarize → Sonnet propose → detect_ats → insert pending
    self_update/
      __init__.py
      summarize_feedback.py   # week's feedback -> FeedbackSummary
      propose_diff.py         # Sonnet -> bounded PatchOp list
      apply_diff.py           # JSON-Pointer-ish patch engine (ruamel) + guardrails
      run.py                  # run_self_update (propose) + apply_proposed (open PR)
    webapp/
      __init__.py
      main.py               # FastAPI app entrypoint
      routes/
        votes.py
        inbox.py
        sources.py
        profile.py
        status.py
      templates/
      static/
      auth.py               # token + session helpers
    obs/
      cost.py               # cost tracking
      runs.py               # run-row helpers
  tests/
    conftest.py
    test_<module>.py
  .github/
    workflows/
      weekly.yml            # cron Sun 07:30 UTC — full pipeline (crawl+rank+digest+discover+self-update)
      ci.yml                # lint + test on PR
  vercel.json               # Python runtime config
```

Step files reference paths inside this layout. If a step calls for a file not yet listed here, add it to the layout in the same PR.

## Python style

- **Ruff config**: target `py312`. Enable rule sets `E, F, I, B, UP, SIM, C4, RET, PT`. Line length 100. Format on save.
- **Type hints required** on all public functions. Use `from __future__ import annotations` at the top of every module.
- **No comments narrating obvious code.** Comments only for non-obvious intent, trade-offs, or upstream-API quirks. Examples of good comments: "Workday returns `null` instead of `[]` for empty job arrays — handle both"; "Anthropic tool-use returns one block per tool call; we only ever issue one." Examples of bad comments: "increment counter," "return result," "loop over jobs."
- **Constants** in `UPPER_SNAKE_CASE` at module top.
- **Pydantic models** for all data crossing a boundary (HTTP, LLM, DB row → app object). Internal helpers can use plain dataclasses if they don't cross a boundary.
- **No global mutable state.** Pass settings explicitly.

## Testing

- Every module that touches HTTP has at least one VCR-based test against a real recorded fixture.
- Every module that calls the LLM has at least one test against a recorded `anthropic` response (use the SDK's mocking utilities or a hand-rolled fake).
- DB tests use a transactional rollback fixture against a `pgtap`-style throwaway schema.
- Acceptance tests for each step live in `tests/acceptance/test_step_NN_*.py`. The step file's "Acceptance criteria" section maps 1:1 to assertions.

## Commits

- Conventional-ish: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`. Title in imperative.
- One step per branch when feasible. Branch name: `step-NN-short-name`.
- PR description includes the step file referenced and a checklist mirroring its acceptance criteria.

## Logging

- Use `structlog` (added in Step 01). Every logger has a context including `run_id` (when inside a scheduled run).
- Log levels: `INFO` for normal progress, `WARNING` for handled-but-notable (e.g., a fetcher returned 0 jobs), `ERROR` for unhandled / re-raised.
- Never log secrets, raw API keys, or full email bodies. Token previews truncated to first 8 chars.

## Agent-prompting conventions

When you (the human) kick off an AI agent on a step, paste this preamble:

> You are executing **Step NN** of the Policy Crawler project.
>
> Read these files in order, end-to-end, before writing any code:
> 1. `docs/00-overview.md`
> 2. `docs/01-architecture.md`
> 3. `docs/03-tech-stack.md`
> 4. `docs/04-conventions.md`
> 5. `docs/02-personal-context.md` (skim unless step touches preferences/ranker/sources)
> 6. `docs/steps/NN-*.md` (the target step)
> 7. All `docs/steps/01-*.md`...`docs/steps/(NN-1)-*.md` (skim)
>
> Build only the deliverables listed in the step's "Deliverables" section. Verify the "Acceptance criteria" before declaring done. If you find a contradiction between docs, stop and ask. Reference docs (01–04) override step files; the overview overrides everything.
>
> Do not run any destructive shell commands. Do not push. Do not commit `.env`. After implementation, run the step's smoke test commands and paste the output.

When the agent finishes, review their changes against the step's acceptance criteria, then commit + push manually.

## Things agents reliably get wrong on this project

Document each as you discover them so the next agent doesn't repeat the mistake.

- **Anthropic tool-use vs. JSON-in-text**: Always use tool-use blocks. Do not parse JSON out of a free-form text response.
- **Vercel Python runtime is stateless**: do not write to `/tmp` expecting persistence across requests. All state is in Postgres.
- **Neon connection pool**: from the webapp use the **pooled** connection string (`-pooler` host); from migration scripts use the direct one.
- **GitHub Actions cron lag**: scheduled runs can be delayed under heavy load. Don't write logic that assumes "the daily run started at exactly 07:00."
- **Workday endpoint discovery**: the JSON endpoint URL is derived from the careers page slug; if the slug changes, the fetcher silently breaks. Log a `WARNING` if a Workday source returns 0 jobs two days in a row.
- **Email-link tokens are single-use**: the vote-recording handler must look up + invalidate atomically (a single SQL `UPDATE … RETURNING`).
- **Posting types are not titles**: don't infer `posting_type` from job title alone. The fetchers should set it from URL pattern + source category, not from `title.contains("fellow")`.
- **`ruff format --check` is read-only**: a newly-`Write`-en Python file will almost always need one pass of `ruff format .` before `ruff format --check .` will exit 0. Run the formatter once after creating/editing files, then run the `--check` form to verify. Don't try to hand-format around ruff's preferences.
- **`get_settings()` is `@lru_cache`-ed**: any test that uses `monkeypatch.setenv(...)` to populate config must call `get_settings.cache_clear()` first (an `autouse` fixture is the clean way) — otherwise the second test in the file reads a stale `Settings` instance from a sibling test.
- **Migrations must use `NEON_DATABASE_URL_DIRECT`**: Neon's pgbouncer (the `-pooler` host) runs in transaction pooling mode and silently breaks DDL that depends on session state. `migrations/_apply.py` reads the direct URL; the app pool (`db.py`) reads the pooled URL. Mixing them up surfaces as "prepared statement does not exist" errors.
- **`get_pool()` is `@cache`-d**: tests that touch the DB must call `get_pool.cache_clear()` in an `autouse` fixture — same pattern as `get_settings`.
- **Corporate egress filters block port 5432**: symptom is TCP handshake succeeds but `psycopg.connect()` fails with `server closed the connection unexpectedly` the moment the Postgres `SSLRequest` packet is sent (L7 proxy drops non-HTTPS). Workarounds: mobile tether, home wifi, or run the migration from CI.
- **Camoufox requires a separate browser download**: `pip install -e ".[camoufox]"` installs the Python package but the patched Firefox binary must be downloaded separately with `python -m camoufox fetch` (~80 MB). The weekly CI workflow does this automatically; local smoke tests require it manually. The import is lazy (`from camoufox.sync_api import Camoufox` inside the function body) so the dev install (`.[dev]`) works fine without the browser.
- **`iCIMS` pages need a longer render wait**: the `#icims_content_iframe` typically takes 12–15 seconds to attach as a browser frame. The default `fetcher_config.wait_seconds = 6` is enough for most pages. For iCIMS sources, set `wait_seconds: 15` in `fetcher_config`.
- **A Camoufox/Playwright driver crash is NOT a Python exception**: the Firefox driver is a Node subprocess. A malformed page `pageError` event can crash it (`TypeError: Cannot read properties of undefined (reading 'url')` in `coreBundle.js`), at which point Node prints a stack trace and `process.exit`s — killing the whole crawl before any `try/except` (or the run's failure-alert) can fire. That's why `camoufox_llm.fetch` calls `render_candidates_isolated`, which runs the render in a spawned child process: a driver crash or hang dies with the child, and the parent logs `camoufox.render_failed` and skips just that one source. Never call `render_candidates` directly from the crawl path — always go through the isolated wrapper.
- **Profile self-update opens its PR via the GitHub REST API, not `git`/`gh`**: the approve action runs in the webapp on Vercel's read-only, repo-less filesystem, so `self_update/run.py:apply_proposed` creates the branch + commit + PR through `api.github.com` with the `GH_PAT_FOR_PROFILE_PR`. It patches the `data/profile.yaml` fetched from `main` (not the bundled copy, which can be stale). The original Step 10 spec's `peter-evans/create-pull-request` / `gh` shellout only makes sense inside an Action, not the serverless webapp.
- **Self-update patch paths are validated, not free-form**: `apply_diff.py` rejects any op touching `version` or `identity.cv_url`, and any op that would leave `must_haves` or `dealbreakers` empty. The model is also told this in the prompt, but the code is the enforcement — don't rely on the prompt alone.
