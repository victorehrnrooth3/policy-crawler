# Step 11 — Observability & Cost Guardrails

## Goal

Make the system legible: per-run cost reports, a daily soft cap that degrades to Haiku-only, failure email alerts, and a `/status` page that surfaces health at a glance.

## Reading list

- `docs/01-architecture.md` (§ "Components" — `runs`, `llm_calls`)
- `docs/03-tech-stack.md`
- `docs/04-conventions.md`
- All step files 01–10 (this step closes the loop on each).

## Inputs / prereqs

- Steps 01–10 complete; the system has run end-to-end at least once.

## Deliverables

### Cost & guardrails

- `src/policy_crawler/obs/cost.py`:
  - `compute_call_cost(model, in_tokens, out_tokens) -> float` — uses prices from a single constants file. Anthropic prices are pinned here:
    ```python
    PRICES_USD_PER_M_TOKENS = {
      "claude-haiku-4-5":    {"input": 1.0,  "output": 5.0},
      "claude-sonnet-4-6":   {"input": 3.0,  "output": 15.0},
    }
    ```
    Update the constants if/when models are swapped. Step 03 doc cites these prices; keep them in sync.
  - `daily_spend(date) -> float` — sums `llm_calls.cost_usd` for the day.
  - `monthly_spend(month) -> float`.
  - `should_degrade_to_haiku(today) -> bool` — true if today's spend ≥ `DAILY_SOFT_CAP_USD` (env, default `$0.30`) **before** Pass 2 starts.
- `src/policy_crawler/ranker/pass2.py`:
  - At the top of `deep_score`, call `cost.should_degrade_to_haiku(today)`. If true, log a structured `WARNING` and run Pass 2 with the **Haiku** model instead of Sonnet (using the same Pass-2 prompt). Mark these rows in `llm_calls.metadata.degraded = true`.
- Settings:
  - `DAILY_SOFT_CAP_USD: float = 0.30` (configurable via env).
  - `MONTHLY_SOFT_CAP_USD: float = 5.0`.
  - `HARD_KILL_USD: float = 2.0` per-run absolute cap. `score_pending` aborts (gracefully) the moment a single run crosses this.

### Failure alerts

- `src/policy_crawler/obs/alerts.py`:
  - `send_failure_email(run_id, kind, error)` — Resend message to `DIGEST_TO_EMAIL` with subject `[policy-crawler] {kind} run failed YYYY-MM-DD HH:MM` and body containing the workflow URL, run id, last 50 lines of stderr captured by the wrapper, and a link to `/status`.
  - `send_warning_email(run_id, body)` — used for "warnings exceeded" cases (e.g., 5+ sources returned 0 jobs). Sent at most once per day.
- Wired into `src/policy_crawler/run.py`: any unhandled exception in the wrapper triggers a failure email before re-raising.

### Status page

- `src/policy_crawler/webapp/routes/status.py` (extended from Step 07):
  - Last 14 daily run rows: started_at, duration, jobs_seen, jobs_new, llm calls, cost, status.
  - Source health table: `name`, `category`, `last_checked_at`, `last_success_at`, gap in days (red if > 3, amber if > 1).
  - Today's spend vs `DAILY_SOFT_CAP_USD`, monthly vs `MONTHLY_SOFT_CAP_USD`.
  - Pending counts: pending suggested sources, pending profile changes.
  - Render server-side, refresh-on-load. No JS auto-refresh.

### Tests

- `tests/obs/test_cost.py` — synthetic `llm_calls` rows; assert daily/monthly sums and `should_degrade` behavior at thresholds.
- `tests/obs/test_alerts.py` — alert composition + dedup-within-day.
- `tests/webapp/test_status.py` — `/status` renders with synthetic data.

## Acceptance criteria

```bash
pytest -q tests/obs/ tests/webapp/test_status.py

# Force a failure:
ANTHROPIC_API_KEY=invalid python -m policy_crawler.run --kind daily
# Expect: failure email to DIGEST_TO_EMAIL, run row marked failed, exit code non-zero.

# Force degradation:
DAILY_SOFT_CAP_USD=0.0001 python -m policy_crawler.ranker.run --kind daily --limit 3
# Expect: pass 2 calls run on Haiku (per llm_calls.model column), with a WARNING log.
```

`/status` page renders: shows today's run summary, cost vs cap, source-health table.

## Implementation notes

- **Cost prices live in one file.** Don't scatter them. When prices change, you change the constants once.
- **Soft cap, not hard cap.** A hard cap that aborts the run silently is worse than degraded results that still arrive. Always log + email when degradation kicks in.
- **`HARD_KILL_USD`** is the only true abort. Keep it generous; a runaway loop is the only thing it should catch.
- **Alert fatigue**: dedupe alerts. Use `runs.metadata.alert_sent_at` so a flapping source doesn't email me 10 times. The alert subject line includes a stable "alert kind" string.
- **No external monitoring.** If GitHub Actions itself is down, the system is silent — that's acceptable for a single-user weekend project. Don't over-engineer this with external watchdogs unless I ask.
- **`/status` is unauthenticated** by design. Only counts and timestamps; nothing personal. If we ever add it, gate the page itself but keep the JSON `/status.json` open for future Slack/Telegram integrations.

## Out of scope

- Building a fancy dashboard (Datadog, Grafana). The simple `/status` page is enough.
- Per-run flame graphs / tracing. Not at this scale.
- A cost prediction model. Pin prices, monitor sums.

## Followups

- Push run summaries to a private Slack/Telegram if I ever add one.
- Add an automatic "open a GitHub issue" path for new failure modes (reuse the GH PAT from Step 10).
- A weekly "system health" email with a 7-day cost graph (text-based sparklines are fine).
