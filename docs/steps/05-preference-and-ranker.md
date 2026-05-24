# Step 05 — Preference Profile & Ranker

## Goal

Bootstrap `data/profile.yaml` from `docs/02-personal-context.md`, then build the two-pass Haiku→Sonnet ranker that scores every unscored job and writes the results back to the `jobs` table.

## Reading list

- `docs/01-architecture.md` (§ "Ranker design", § "Posting-type taxonomy")
- `docs/02-personal-context.md` (whole file — this is the input data)
- `docs/03-tech-stack.md` (LLM choices, structured-output requirement)
- `docs/04-conventions.md` ("Things agents reliably get wrong" — Anthropic tool-use)
- `docs/steps/03-source-registry.md`, `docs/steps/04-crawler-framework.md`

## Inputs / prereqs

- Steps 01–04 complete.
- `ANTHROPIC_API_KEY` set in `.env`.
- `jobs` table contains some rows from a real `crawl_all()` run.

## Deliverables

### Profile

- `data/profile.yaml` — initial preference profile transcribed from `docs/02-personal-context.md`. Schema:

  ```yaml
  version: 1
  identity:
    summary: |
      Free-text summary of who I am and what I'm looking for.
    cv_url: "https://victorehrnrooth.com"
  career_thesis: |
    Free-text thesis (1-2 paragraphs).
  topics:
    heavy:
      - name: "energy economics & energy transition"
        keywords: ["..."]
      - ...
    medium: [...]
    low: [...]
    negative:
      - name: "pure finance / IB"
        keywords: ["..."]
  geography:
    primary: ["london"]
    secondary: ["nyc", "bay_area", "boston", "dc", "chicago"]
    acceptable: ["paris", "brussels", "geneva", "helsinki", "remote_global"]
    timeline_note: "London now; US ~12 months out."
  must_haves:
    - "Topic match to at least one heavy or medium topic"
    - ...
  dealbreakers:
    - "US role with explicit no-sponsorship language"
    - ...
  soft_negatives:
    - "Slow-bureaucratic-only environments"
    - ...
  exemplars:
    liked:
      - title: "Eurasia Group, Geo-technology Practice, Analyst"
        why: "..."
        topic: "geopolitics × tech"
      - ...
    disliked:
      - title: "Goldman Sachs IB Analyst"
        why: "..."
  ```

- `src/policy_crawler/ranker/profile.py`:
  - `Profile` Pydantic model mirroring the schema.
  - `load_profile(path="data/profile.yaml") -> Profile`.
  - `profile_for_prompt(profile: Profile) -> str` — renders the profile to a markdown string trimmed to a token budget (the Anthropic SDK exposes a token counter; aim for ≤ 1 500 input tokens for the profile alone).

### Schemas

- `src/policy_crawler/ranker/schemas.py` — Anthropic tool-use schema for both passes:

  ```python
  PASS1_TOOL = {
    "name": "score_pass1",
    "description": "Cheap screen of a single job posting against the user's preference profile.",
    "input_schema": {
      "type": "object",
      "properties": {
        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "posting_type": {"type": "string", "enum": ["role","fellowship","predoc","program_call","internal_rotation","unknown"]},
        "geography_match": {"type": "string", "enum": ["primary","secondary","acceptable","mismatch","unknown"]},
        "dealbreaker_hits": {"type": "array", "items": {"type": "string"}},
        "screen_reason": {"type": "string"}
      },
      "required": ["fit_score","confidence","posting_type","geography_match","dealbreaker_hits","screen_reason"]
    }
  }

  PASS2_TOOL = {
    "name": "score_pass2",
    "description": "Deep score and explanation for a single job posting that passed the screen.",
    "input_schema": {
      "type": "object",
      "properties": {
        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "reason_to_consider": {"type": "string"},
        "concerns": {"type": "string"},
        "matched_signals": {"type": "array", "items": {"type": "string"}},
        "missing_info": {"type": "array", "items": {"type": "string"}},
        "recommended_action": {"type": "string", "enum": ["apply_now","monitor","skip","needs_human_review"]}
      },
      "required": ["fit_score","reason_to_consider","concerns","matched_signals","missing_info","recommended_action"]
    }
  }
  ```

### Prompts

- `src/policy_crawler/ranker/prompts.py`:
  - `pass1_prompt(profile_md, job, exemplars) -> str` — ≤ ~3k tokens. Includes profile, 3 liked + 3 disliked exemplars (rendered concisely), then the job (title + company + location + first ~1500 chars of `description_clean`).
  - `pass2_prompt(profile_md, job, recent_feedback_summary, exemplars) -> str` — adds a longer description excerpt (~4k chars) and a "recent feedback" section listing the last 5–10 votes with free-text feedback.
  - System prompt baseline: "You are a calibrated, skeptical evaluator scoring job postings against a user's preference profile. Be concise. Use the tool to return your judgment — never reply in free-form text. If a dealbreaker hits, the score should be ≤ 30."

### Two passes

- `src/policy_crawler/ranker/pass1.py`:
  - `screen(jobs: list[JobRow]) -> list[Pass1Result]`:
    - For each job, build prompt, call `messages.create` with `model = haiku`, `tools = [PASS1_TOOL]`, `tool_choice = {"type": "tool", "name": "score_pass1"}`, `max_tokens = 256`.
    - Persist result to `jobs` columns and write a row to `llm_calls`.
  - One retry on tool-output schema failure with a stricter system prompt addendum. After two failures, log + skip.

- `src/policy_crawler/ranker/pass2.py`:
  - `deep_score(jobs: list[JobRow]) -> list[Pass2Result]`:
    - Inclusion criteria: `pass1_score >= 60` OR `pass1_confidence == 'low'` OR source `priority == 5`.
    - Calls Sonnet with the larger prompt; persists; logs cost.

### Orchestration

- `src/policy_crawler/ranker/run.py`:
  - `score_pending(run_id) -> RankerSummary`:
    - Selects jobs where `pass1_score IS NULL` from the most recent crawl run, runs Pass 1.
    - Then selects jobs eligible for Pass 2 from the same set (and any earlier-skipped borderline rows up to N days old), runs Pass 2.
    - Hard cap: `MAX_PASS1_PER_RUN = 200`, `MAX_PASS2_PER_RUN = 30`. If exceeded, log a warning; do not silently drop — pick highest-priority sources first.
  - CLI: `python -m policy_crawler.ranker.run --kind daily`.

### Tests

- `tests/ranker/test_profile.py` — loading the YAML, validating, rendering for prompts.
- `tests/ranker/test_schemas.py` — schema is valid JSON Schema.
- `tests/ranker/test_pass1.py` — uses recorded Anthropic responses (fake `Anthropic` client) for two synthetic jobs and one known-dealbreaker job; asserts dealbreaker → low score.
- `tests/ranker/test_pass2.py` — similar; one borderline job, one strong fit.
- `tests/ranker/test_run.py` — end-to-end against the test DB with Anthropic mocked; asserts cost cap and Pass-2 inclusion logic.

## Acceptance criteria

```bash
pytest -q tests/ranker/

# Real run on real data (small sample):
python -m policy_crawler.ranker.run --kind daily --limit 20
```

After the real run:

```sql
SELECT count(*) FILTER (WHERE pass1_score IS NOT NULL) AS p1,
       count(*) FILTER (WHERE pass2_score IS NOT NULL) AS p2,
       count(*) FROM jobs;
-- Expect: p1 high, p2 lower, all reasonable.

SELECT title, company, pass1_score, pass2_score, pass2_recommended_action
FROM jobs WHERE pass2_score IS NOT NULL
ORDER BY pass2_score DESC LIMIT 10;
-- Eyeball: do the top results look like things I'd actually want?

SELECT model, sum(input_tokens), sum(output_tokens), sum(cost_usd)
FROM llm_calls
WHERE created_at > now() - interval '1 hour'
GROUP BY model;
-- Expect: cost well under $0.20 for a 20-job run.
```

## Implementation notes

- **Tool use, not JSON-in-text.** The Anthropic SDK returns content blocks; iterate to find the `tool_use` block and read `block.input`.
- **`tool_choice`**: explicit `{"type": "tool", "name": "..."}` to force the call. Without this the model sometimes responds in plain text.
- **Token counting**: use `client.messages.count_tokens` (or estimate via `len(text) / 4`) before the call to abort early if a job description is huge — truncate to ~6 000 chars before sending.
- **Cost calc**: hard-code per-1M token prices from `docs/03-tech-stack.md` (Haiku $1/$5; Sonnet $3/$15). Compute `cost_usd = (input_tokens/1e6)*input_price + (output_tokens/1e6)*output_price` per call.
- **Exemplar selection**: from `feedback`, pick the 3 most recent up-votes with non-empty `freetext` (ranked by recency × strength) and 3 most recent down-votes; fall back to the seed exemplars in `profile.yaml` if not enough feedback exists.
- **Recent-feedback summary**: a one-liner per recent vote: `"[UP] Eurasia Group Geo-tech analyst — 'liked the topic + cohort'"`. Cap at 10 entries totaling ≤ 600 tokens.
- **Don't include the full `02-personal-context.md`** in the prompt. The profile is the runtime artifact; the personal-context doc is the bootstrap source.
- **Dealbreaker handling**: prompt instructs the model to map any dealbreaker hit to `fit_score ≤ 30`. Verify in tests.
- **Posting-type override**: if `jobs.posting_type` was set by the normalizer to something other than `unknown`, the model is told to **respect** it in `pass1.posting_type`. This avoids the model "deciding" something is a fellowship just because the title contains "fellow."
- **Concurrency**: process jobs sequentially in v1. The Anthropic SDK supports async; defer until cost or latency demands it.

## Out of scope

- Self-updating the profile (Step 10).
- Source discovery (Step 09).
- The digest's selection logic for which jobs to surface (Step 06).
- Confidence calibration / eval harness — comes back in Step 11 if needed.

## Followups

- Add an offline eval set (a held-out set of past jobs with my labels) for measuring drift after profile updates.
- Consider a small classical ranker (logistic regression) on top of LLM features once we have ≥ 100 labeled jobs. Defer.
