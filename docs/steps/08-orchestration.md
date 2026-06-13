# Step 08 — Orchestration

## Goal

Wire the full pipeline behind GitHub Actions cron so the daily and weekly jobs run unattended.

## Reading list

- `docs/01-architecture.md` (§ "Components" — daily and weekly flows; `runs` / `llm_calls` schema)
- `docs/03-tech-stack.md` (GitHub Actions; secrets list)
- `docs/04-conventions.md`
- All step files 01–07 (skim — you're orchestrating their CLIs).

## Inputs / prereqs

- Steps 01–07 complete and individually working from a developer machine.
- All required secrets added to **Repository → Settings → Secrets and variables → Actions** (matching the list in `docs/03-tech-stack.md`).
- Vercel deployment live (so the digest's links resolve).

## Deliverables

### Workflows

- `.github/workflows/ci.yml` — runs on PR + push to `main`. Steps: checkout, set up Python 3.12, `pip install -e .[dev]`, `ruff check`, `ruff format --check`, `pyright`, `pytest -q`. Cache `~/.cache/pip` and the `.venv` keyed on `pyproject.toml` hash.
- `.github/workflows/daily.yml` — schedule cron `15 6 * * *` (06:15 UTC; ~7:15 London / 8:15 CEST in winter). Single job that:
  1. Checkout, set up Python.
  2. `pip install -e .` (no dev deps in the runner — keeps it fast).
  3. Run a small wrapper `python -m policy_crawler.run --kind daily` which sequences:
     - Open a `runs` row.
     - `crawler.run.crawl_all(run_id=...)`
     - `ranker.run.score_pending(run_id=...)`
     - `digest.send.send_digest()`
     - Close the `runs` row.
     - On any unhandled exception: mark `runs.status = failed`, send a failure email via Resend (Step 11 expands this), re-raise to fail the workflow.
  4. `workflow_dispatch` trigger so I can run on demand from the GitHub UI.
- `.github/workflows/weekly.yml` — schedule cron `30 7 * * 0` (Sundays 07:30 UTC). Two sequential `python -m policy_crawler.run --kind` invocations: `weekly_discovery` then `weekly_self_update`. Each writes its own `runs` row.

### Wrapper

- `src/policy_crawler/run.py`:
  - A single CLI that dispatches by `--kind` to the appropriate sequence.
  - Provides shared `run_row` lifecycle helpers used by all sub-steps.

### Run row helpers

- `src/policy_crawler/obs/runs.py`:
  - `start_run(kind, metadata) -> run_id`.
  - `finish_run(run_id, status, summary)`.
  - Adds entries to `metadata` jsonb such that the `/status` page can show what happened.

### Tests

- `tests/test_run_wrapper.py` — uses fakes to assert that `run.py --kind daily` invokes crawler → ranker → digest in order, opens and closes a `runs` row, and on a forced exception in any subsection still closes the row.

## Acceptance criteria

```bash
# Locally:
python -m policy_crawler.run --kind daily
# End-to-end success; an email arrives; runs and llm_calls populated.
```

In GitHub Actions:

- A manual `workflow_dispatch` of `daily.yml` succeeds end-to-end.
- After 24h with cron enabled, a scheduled run has succeeded.
- A manual `workflow_dispatch` of `weekly.yml` runs both subjobs (some may fail until Steps 09 / 10 are implemented; this step's acceptance is that the wrapper opens / closes `runs` rows correctly even on failure).
- The CI workflow is green on PRs.

## Implementation notes

- **Cron timing**: GitHub-hosted runner schedules can be delayed at peak times. Don't write logic that assumes "the run started at exactly 06:15 UTC." `runs.started_at` is the truth.
- **Concurrency**: Use `concurrency: { group: daily, cancel-in-progress: false }` so a slow run doesn't get killed by the next day's start. Same for weekly with a separate group.
- **Caching**: Cache pip wheels keyed on `${{ hashFiles('pyproject.toml') }}`. Don't cache `.venv` directly across runners (path differences across OS); cache only the wheel cache.
- **Failure surfacing**: On failure, send an email to `DIGEST_TO_EMAIL` with subject `[policy-crawler] daily run failed YYYY-MM-DD` and body containing the workflow URL + last 50 lines of logs (use `tail -n 50 $GITHUB_STEP_SUMMARY` or capture via Python). Step 11 hardens this.
- **Cost cap kill switch**: a config flag in `Settings`, `RANKER_DEGRADE_TO_HAIKU_ONLY`. If true, `pass2.deep_score` is a no-op. Step 11 wires this to the actual cost computation; for now just expose the flag.
- **Don't run weekly jobs on the daily schedule.** They share the wrapper but distinct workflows + distinct cron lines keep the schedule readable.
- **Profile self-update PR creation** (used by Step 10): the wrapper exposes a `--gh-pat` arg so the weekly self-update job can open a PR. The PAT lives in `GH_PAT_FOR_PROFILE_PR`.

## Out of scope

- Implementing the discovery and self-update jobs (Steps 09, 10).
- Detailed cost dashboards (Step 11).
- Per-source rate-limit-aware scheduling (a Followup if usage demands).

## Followups

- Pin runner OS for reproducibility (`ubuntu-24.04` rather than `ubuntu-latest`).
- Consider self-hosted runners only if Anthropic egress / Neon connectivity becomes flaky on GH-hosted.

## As-built departures

The implementation diverges from this spec in two ways. Future agents should treat the code as authoritative, not this section.

**`daily.yml` was removed.** The production schedule is a single `weekly.yml` cron (Sundays 07:30 UTC). The spec described `daily.yml` for crawl+rank+digest and `weekly.yml` for two sequential discovery/self-update invocations. That two-workflow design was simplified when Camoufox was added (it requires a browser download step that only makes sense in a weekly budget). The `daily`, `weekly_discovery`, and `weekly_self_update` `--kind` values remain in `run.py` for ad-hoc `workflow_dispatch` and CLI use.

**`weekly.yml` runs one unified `--kind weekly` invocation**, not two sequential `--kind weekly_discovery; --kind weekly_self_update` calls. The `weekly` pipeline sequences: `crawl_all → score_pending → send_digest → run_discovery → _run_weekly_self_update`. It installs `.[camoufox]` and runs `python -m camoufox fetch` before the pipeline step.

**`RANKER_DEGRADE_TO_HAIKU_ONLY`** — the flag exists in `config.py` and is checked by `pass2.py`, but with weekly-only runs and a full cost budget, it should not be set in GitHub Secrets. It was a temporary workaround when the ranker backlog was being cleared on a daily schedule.
