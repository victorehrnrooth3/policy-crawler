# Step 05 — Live Scoring Verification

**Branch:** `step-05-ranker`
**Status:** Code complete, committed, pushed. Needs API key + live run to close out.

---

## What was built

| File | Purpose |
|---|---|
| `data/profile.yaml` | Preference profile: identity, career thesis, heavy/medium/low/negative topics, geography, must-haves, dealbreakers, 10 liked + 5 disliked exemplars |
| `src/policy_crawler/ranker/profile.py` | Pydantic model + `load_profile()` + `profile_for_prompt()` + `format_exemplars()` |
| `src/policy_crawler/ranker/schemas.py` | `PASS1_TOOL` and `PASS2_TOOL` Anthropic tool-use dicts (typed as `ToolParam`) |
| `src/policy_crawler/ranker/prompts.py` | `SYSTEM_PROMPT`, `pass1_prompt()`, `pass2_prompt()`, `format_recent_feedback()` |
| `src/policy_crawler/ranker/pass1.py` | Haiku 4.5 screen — cheap pass over every unscored job |
| `src/policy_crawler/ranker/pass2.py` | Sonnet 4.6 deep score — runs on jobs with pass1 ≥ 60, low confidence, or priority 5 |
| `src/policy_crawler/ranker/run.py` | Orchestrator + CLI (`--limit`, `--kind`) |
| `tests/ranker/` | 56 tests, all passing (1 skipped without DB) |

All linters clean: `ruff format/check` and `pyright` exit 0.

---

## Pre-flight checklist

- [ ] On the `step-05-ranker` branch (or pull it: `git fetch && git checkout step-05-ranker`)
- [ ] `.venv` exists and is activated (see below if not)
- [ ] `ANTHROPIC_API_KEY` populated in `.env`
- [ ] `NEON_DATABASE_URL` populated in `.env` (should already be set from Steps 02–04)

### Set up venv if needed

```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# Mac/Linux:
source .venv/bin/activate

pip install -e .[dev]
```

### Populate `.env`

Open `.env` and fill in the empty values:

```env
ANTHROPIC_API_KEY=sk-ant-...          # your Anthropic key
NEON_DATABASE_URL=postgresql://...    # pooled Neon URL (already set if Steps 02-04 ran)
```

---

## Run the tests first (sanity check)

```bash
pytest -q tests/ranker/
# Expected: 56 passed, 1 skipped
```

---

## Live scoring run (20-job sample)

```bash
python -m policy_crawler.ranker.run --limit 20
```

Expected output (approximate):

```
ranker.pass1.start count=20
ranker.pass1.done scored=20 cost=0.00XXXX
ranker.pass2.start count=N       # N = jobs with pass1>=60 or low confidence
ranker.pass2.done scored=N cost=0.00XXXX
ranker.done pass1=20 pass2=N total_cost=0.0XXXX
Ranker done: pass1=20, pass2=N, cost=$0.0XXX
```

If Pass 1 scores all 20 and roughly half clear the ≥60 threshold, Pass 2 will score ~5–15 of them.

---

## Verify results in Neon SQL editor

Open your [Neon dashboard](https://console.neon.tech/) → SQL editor → run these:

### 1. Score counts

```sql
SELECT
    count(*) FILTER (WHERE pass1_score IS NOT NULL) AS pass1_scored,
    count(*) FILTER (WHERE pass2_score IS NOT NULL) AS pass2_scored,
    count(*) AS total
FROM jobs;
```

Expected: `pass1_scored = 20`, `pass2_scored > 0`, `total = 582` (or close).

### 2. Top-scored jobs

```sql
SELECT title, company, location_raw,
       pass1_score, pass2_score, pass2_recommended_action
FROM jobs
WHERE pass2_score IS NOT NULL
ORDER BY pass2_score DESC
LIMIT 10;
```

Sanity check: top results should be recognisable policy/research/think-tank roles, not finance or ops.

### 3. Cost breakdown by model

```sql
SELECT model,
       sum(input_tokens)  AS total_input,
       sum(output_tokens) AS total_output,
       round(sum(cost_usd)::numeric, 6) AS total_cost_usd
FROM llm_calls
WHERE created_at > now() - interval '1 hour'
GROUP BY model
ORDER BY total_cost_usd DESC;
```

Expected: two rows — one for `claude-haiku-4-5-20251001` (Pass 1) and one for `claude-sonnet-4-6` (Pass 2). Haiku should be cheap (<$0.005 for 20 jobs); Sonnet a bit more.

---

## If something goes wrong

| Symptom | Fix |
|---|---|
| `RuntimeError: ANTHROPIC_API_KEY not set` | Add the key to `.env` |
| `RuntimeError: NEON_DATABASE_URL not set` | Add the Neon pooled URL to `.env` |
| `pass1.no_tool_use` warnings in log | Normal — the retry kicks in. If it persists on every job, check model name in `pass1.py` |
| `pass2.api_error` | Rate limit or network issue — re-run with `--limit 5` to test |
| `pass1_scored = 0` after run | DB already fully scored from a prior run, or no unscored jobs. Check `SELECT count(*) FROM jobs WHERE pass1_score IS NULL` |
| Scores look wrong (e.g., finance jobs scoring 80+) | Review `data/profile.yaml` dealbreakers and topic weights; re-run after editing |

---

## After verification

Once the 3 SQL queries above look sensible:

1. Merge to main:

```bash
git checkout main
git merge step-05-ranker
git push origin main
```

2. Update `docs/STATUS.md` — mark Step 05 as **Done, merged to main** and record the first scoring stats (jobs scored, total cost).

3. Proceed to Step 06 — Digest selection & email sender.
