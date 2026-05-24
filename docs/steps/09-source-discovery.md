# Step 09 — Source Discovery

## Goal

Once a week, propose new employers to monitor based on patterns in my likes/dislikes. Verify the suggestions are real and reachable, then queue them for my approval in the webapp. Never auto-add.

## Reading list

- `docs/01-architecture.md` (§ "Source discovery")
- `docs/02-personal-context.md`
- `docs/04-conventions.md`
- `docs/steps/05-preference-and-ranker.md`, `docs/steps/07-vote-endpoint-and-webapp.md` (the approval surface)

## Inputs / prereqs

- Steps 01–08 complete; some real feedback rows exist (the system has been running for at least a few days). For early testing, hand-seed `feedback` with synthetic up/down votes to validate the flow.

## Deliverables

- `src/policy_crawler/discovery/summarize_likes.py`:
  - `build_summary(window_days=30) -> LikeSummary`:
    - Top 20 up-voted jobs in window with: title, company, source category, posting type, geography, fit score, free-text snippet.
    - Top 20 down-voted jobs in window with the same fields.
    - Aggregates: counts per source category, per topic keyword (tokenize titles + descriptions, count against `profile.topics.heavy.keywords`), per geography.
- `src/policy_crawler/discovery/propose_sources.py`:
  - `propose(summary: LikeSummary, k: int = 15) -> list[CandidateSource]`:
    - Sonnet 4.6 call with a tool-use schema:
      ```python
      PROPOSE_TOOL = {
        "name": "propose_sources",
        "description": "Propose new employers to monitor based on user's preference patterns.",
        "input_schema": {
          "type": "object",
          "properties": {
            "candidates": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "name": {"type": "string"},
                  "homepage_url": {"type": "string"},
                  "careers_url": {"type": "string"},
                  "category": {"type": "string", "enum": [...]},  # source_category enum
                  "rationale": {"type": "string"},
                  "example_similar_jobs": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["name","homepage_url","careers_url","category","rationale","example_similar_jobs"]
              }
            }
          },
          "required": ["candidates"]
        }
      }
      ```
    - Prompt includes: the LikeSummary, the current active source list (as a text dump grouped by category — to avoid duplicates), and the relevant section of `02-personal-context.md` (geography + topics).
    - System message stresses: do not propose sources I already monitor; favor employers, not aggregators (no LinkedIn, no Indeed); propose `careers_url`s I can verify; when in doubt about a `careers_url`, prefer the homepage and let the validator find the careers page.
- `src/policy_crawler/discovery/validate.py`:
  - `validate(candidate: CandidateSource) -> ValidationResult`:
    - HEAD/GET the `careers_url` (follow redirects); reject if non-2xx.
    - URL-pattern match for `fetcher_kind` (same heuristics as Step 03).
    - Light heuristic: page text contains words like "careers", "join", "open positions", "jobs" → confidence boost.
    - Returns either `(ok, suggested_fetcher_kind)` or `(reason_for_rejection, None)`.
- `src/policy_crawler/discovery/run.py`:
  - `run_discovery(run_id) -> DiscoverySummary`:
    - `summary = build_summary(); candidates = propose(summary, k=15); for c in candidates: r = validate(c); insert into suggested_sources`.
    - Skip candidates whose `homepage_url` matches an existing source (case-insensitive normalized).
    - Limit total inserted to 10 per run; remainder go to log only.
  - CLI: `python -m policy_crawler.discovery.run`. Hooked into the weekly workflow in Step 08.
- `tests/discovery/test_*.py`:
  - `test_summarize.py` with synthetic feedback rows.
  - `test_propose.py` with mocked Sonnet response asserting the schema is parsed.
  - `test_validate.py` with mocked HTTP.
  - `test_run.py` end-to-end with mocks; asserts dedupe against existing sources.

## Acceptance criteria

```bash
# With at least a few rows of synthetic feedback:
python -m policy_crawler.discovery.run
```

```sql
SELECT name, careers_url, category, status, rationale FROM suggested_sources
WHERE status = 'pending' ORDER BY proposed_at DESC LIMIT 20;
-- Expect: 5-10 candidates with sensible names, valid URLs, reasonable rationales.
```

In the webapp `/sources` "suggested" tab, the entries appear and approve/reject buttons work; approving a candidate causes it to appear in `sources` with `enabled = true, approved_by_me = true`.

## Implementation notes

- **Source-list summary in the prompt**: render the active sources as a compact list grouped by category, ≤ ~1 500 tokens. The model will dedupe better if it sees the structure rather than a flat dump.
- **Avoid aggregators**: explicit negative instruction. Reject in `validate()` if URL host matches `linkedin.com`, `indeed.com`, `glassdoor.com`, `ziprecruiter.com`, `welcometothejungle.com`.
- **Confidence**: persist a `confidence` field on `suggested_sources` (low/med/high) based on validator signals. `/sources` UI surfaces it as a small badge.
- **Don't auto-promote**, ever. The schema constraint `approved_by_me` exists to prevent this; the discovery code never sets `enabled = true` on `sources` directly.
- **Cost**: weekly, one Sonnet call; ~$0.05–0.10/week. Negligible.
- **Stale candidates**: any `pending` candidate older than 60 days is auto-snoozed via a SQL `UPDATE` at the start of each discovery run.

## Out of scope

- Configuring selectors for newly-approved `generic_html` sources — the human (or the followup LLM-assisted configure) handles that on first crawl error.
- Discovery for new fellowships / PhD program calls is a useful followup but not in v1.

## Followups

- An LLM-assisted "configure selectors" mode that runs immediately after I approve a `generic_html` source.
- Track conversion rate: of suggested sources approved, what fraction produce up-voted jobs within 30 days? Use this to refine the proposal prompt.
