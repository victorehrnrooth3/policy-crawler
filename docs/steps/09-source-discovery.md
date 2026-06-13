# Step 09 — Source Discovery

## Status

**Done** (functionally complete). `discovery/run.py` ships in `step-09-source-config`. Acceptance criteria below are met. Step 10 is the next step to implement.

See "As-built departures" at the bottom for differences between this spec and what was built.

---

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

- `src/policy_crawler/discovery/run.py`:
  - `run_discovery(run_id) -> DiscoverySummary`:
    - Reads recent votes (last 30 days), existing source names, and pending suggestions from DB.
    - Calls Sonnet 4.6 with a forced `suggest_sources` tool → 10–20 `{name, careers_url, category, rationale, example_similar_jobs}` candidates.
    - For each candidate not already a live source or pending suggestion: calls `detect_ats(careers_url)`. If `det.kind == "unknown"` (hard fetch failure), skips. Otherwise: `fetcher_kind = det.kind if det.detected else "camoufox"`.
    - Inserts survivors into `suggested_sources` with `status = 'pending'`. Never auto-adds to `sources`.
    - Logs one `llm_calls` row (kind `discovery`) per run.
  - CLI: `python -m policy_crawler.discovery.run`.
- `tests/discovery/test_discovery.py`:
  - Stubs Sonnet response + `detect_ats`; asserts dedupe against existing sources, `camoufox` fallback when no ATS detected, skip on unreachable URL.

## Acceptance criteria

```bash
python -m policy_crawler.discovery.run
```

```sql
SELECT name, careers_url, category, fetcher_kind, status, rationale
FROM suggested_sources
WHERE status = 'pending'
ORDER BY proposed_at DESC
LIMIT 20;
-- Expect: sensible names, valid URLs, fetcher_kind = detected ATS or 'camoufox', reasonable rationales.
```

In the webapp `/sources` "suggested" tab: entries appear; approve/reject buttons work; approving a candidate inserts it into `sources` with `enabled = true`, `fetcher_kind = COALESCE(suggestion.fetcher_kind, 'camoufox')`.

## Implementation notes

- **`camoufox` as default**: when `detect_ats` returns `kind = "generic_html"` (i.e., no known ATS detected but the page is reachable), use `fetcher_kind = "camoufox"`. Never fall back to `generic_html` for newly-discovered sources — Camoufox is the long-tail strategy.
- **Dedupe guard covers both live sources and pending queue.** Build `known_names` and `known_urls` sets from `sources` + `suggested_sources WHERE status='pending'` before processing candidates. Update these sets within the loop so two proposals in the same batch don't both insert.
- **Skip, don't error, on unreachable URLs.** `detect_ats` returns `kind = "unknown"` when the URL is a hard 404/DNS failure. Increment `skipped_unreachable` and continue.
- **Prompt construction**: include `profile_for_prompt(load_profile())` + recent votes as context + the list of existing source names as a dedupe guard. The prompt instructs Sonnet to propose employers not aggregators.
- **Cost**: one Sonnet call per weekly run; ~$0.20/mo. Log via `_log_llm_call` (same pattern as `camoufox_llm.py`).

## Out of scope

- Configuring selectors for newly-approved sources — `camoufox` handles any page with no extra config.
- Discovery for new fellowships / PhD program calls — useful followup but not in v1.

## Followups

The following spec items were deferred to keep the initial implementation lean. They are candidates for a future maintenance session, not blockers for Step 10.

- **`confidence` field on `suggested_sources`** (low/med/high badge in `/sources` UI). The DB schema and the webapp route would both need updating.
- **60-day auto-snooze**: at the start of each discovery run, `UPDATE suggested_sources SET status = 'snoozed' WHERE status = 'pending' AND proposed_at < now() - interval '60 days'`.
- **Aggregator URL rejection**: in the loop, skip candidates whose `careers_url` host matches `linkedin.com`, `indeed.com`, `glassdoor.com`, `ziprecruiter.com`, `welcometothejungle.com`. The current prompt instructs Sonnet against these but there is no code enforcement.
- **`homepage_url` field**: the spec proposed storing `homepage_url` separately and deduping by it. Currently we only dedupe by name (case-insensitive) + careers URL. Low-risk gap since `name` dedupe is the stronger signal.
- **Structured `LikeSummary` dataclass**: the spec originally called for `summarize_likes.py` to build a typed `LikeSummary` with top-20 up/down-voted jobs before the Sonnet call. Currently we pass raw recent-vote rows directly to the prompt. If prompt quality degrades as feedback volume grows, extracting a structured pre-summary step is the fix.
- **Conversion tracking**: of suggested sources approved, what fraction produce up-voted jobs within 30 days? This informs prompt refinement. Requires a `conversion_metric` or join on `feedback` + `jobs` + `sources`.

## As-built departures

This section documents how the implementation differs from the spec above. The code is authoritative; this section explains the delta.

**Single module, not three.** The spec called for `discovery/summarize_likes.py` + `discovery/propose_sources.py` + `discovery/validate.py` + `discovery/run.py`. Everything lives in `discovery/run.py`. The pipeline steps are identical; the module boundaries were dropped for simplicity.

**`detect_ats` replaces a custom validator.** The spec's `validate.py` described HEAD/GET + text heuristics. Instead, `detect_ats()` from `crawler/detect.py` is reused — it probes the URL for known ATS patterns, falls back to `generic_html` if reachable but unrecognized, and returns `kind = "unknown"` on hard failure. This is strictly better than a bespoke validator.

**Approval default changed to `camoufox`.** The webapp's approve-suggestion route previously inserted `COALESCE(fetcher_kind, 'generic_html')`. Changed to `COALESCE(fetcher_kind, 'camoufox')` so an approved suggestion that only needed Sonnet's URL guess (no detected ATS) starts crawling on the next weekly run with zero manual config.

**Tests consolidated.** One `tests/discovery/test_discovery.py` file rather than four separate test files. Coverage of the key behaviors (dedupe, camoufox fallback, skip-unreachable) is identical.
