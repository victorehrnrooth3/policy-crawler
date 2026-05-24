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
      greenhouse.py
      lever.py
      ashby.py
      workday.py
      rss.py
      sitemap.py
      generic_html.py
      playwright.py
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
      summarize_likes.py
      propose_sources.py
      validate.py
    self_update/
      __init__.py
      summarize_feedback.py
      propose_diff.py
      apply_diff.py
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
      daily.yml
      weekly.yml
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
