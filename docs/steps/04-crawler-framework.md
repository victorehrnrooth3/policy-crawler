# Step 04 — Crawler Framework

## Goal

Build the tiered fetcher framework, normalizer, deduper, and a single `crawl_all()` entrypoint that walks every enabled source, pulls postings, and lands deduplicated rows in the `jobs` table.

## Reading list

- `docs/01-architecture.md` (§ "Fetcher tiers", § "Components", § "Data model" — `jobs`, `job_versions`)
- `docs/02-personal-context.md` (skim — for posting-type intuitions)
- `docs/03-tech-stack.md`
- `docs/04-conventions.md`
- `docs/steps/02-database.md`
- `docs/steps/03-source-registry.md`

## Inputs / prereqs

- Steps 01–03 complete; `sources` table populated.
- No LLM access needed in this step (LLM extraction for `manual` sources comes in Step 07 webapp).

## Deliverables

### Types and base

- `src/policy_crawler/crawler/base.py`:
  - `RawJob` Pydantic model with: `canonical_id`, `url`, `title`, `company`, `location_raw`, `description_raw`, `description_html`, `posting_type` (default `unknown`), `compensation` (optional jsonb), `seen_at` (defaulted to now), and an open `extra: dict` for source-specific fields.
  - `Fetcher` abstract base class:
    - `kind: ClassVar[FetcherKind]`
    - `def fetch(source: SourceRow) -> Iterable[RawJob]`
    - `def configure(source: SourceRow) -> dict` — optional one-time selector inference for `generic_html` (returns updated `fetcher_config`); raises `NotImplementedError` by default.
- `src/policy_crawler/crawler/registry.py`:
  - `FETCHERS: dict[FetcherKind, type[Fetcher]]`
  - `get_fetcher(kind) -> Fetcher`

### Tier-1 / Tier-2 fetchers (real APIs)

- `greenhouse.py` — call `https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true`, paginate via the API's natural pagination, set `canonical_id` to the Greenhouse job id.
- `lever.py` — `https://api.lever.co/v0/postings/{company}?mode=json`. `canonical_id` = lever id.
- `ashby.py` — `https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true`. `canonical_id` = ashby id.
- `smartrecruiters.py` — `https://api.smartrecruiters.com/v1/companies/{company}/postings`. Paginate.
- `workday_json.py` — discover endpoint from careers URL pattern (`https://{tenant}.myworkdayjobs.com/{site}` → `https://{tenant}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`); POST with empty filter. Handle pagination via `offset` + `limit`.
- `workable.py` — try the public API; fall back to `generic_html` if the company has access disabled.

### Tier-3 / Tier-4

- `rss.py` — parse RSS/Atom; `canonical_id` from `<guid>` or hash of `<link>`. Use `feedparser`.
- `sitemap.py` — fetch `sitemap.xml`, filter URLs by a configured regex (e.g., `/careers/`), then for each URL fetch and extract title from `<title>`.
- `generic_html.py` — `httpx` + `selectolax`. Driven entirely by `fetcher_config.selectors` (`list_selector`, `title_selector`, `url_selector`, optional `location_selector`, optional `description_selector`). `canonical_id` = sha1 of absolute URL.

### Tier-5 / Tier-6

- `playwright.py` — same selector contract as `generic_html` but renders the page in headless Chromium first. Add a `playwright` extra in `pyproject.toml` (already specified in Step 01). The fetcher imports lazily so the default install doesn't need it.
- `manual.py` — `fetch()` returns no jobs (it's filled by the webapp's "paste a URL" flow, not by the crawler). Implement as a no-op so `crawl_all()` can iterate cleanly.

### Pipeline

- `src/policy_crawler/crawler/normalize.py`:
  - `normalize(raw: RawJob, source: SourceRow) -> JobRow`:
    - Compute `description_clean` from `description_html` via `markdownify` (add to deps if needed).
    - Detect `remote_policy` from text patterns ("remote", "hybrid", explicit office mentions).
    - Detect `seniority` from title regex (cheap heuristic; LLM ranker can refine).
    - Compute `posting_type` based on (a) source `category` (e.g., `predoc_program` → `predoc`), (b) URL pattern, (c) keyword fallback. Never overwrite an explicit `RawJob.posting_type`.
    - Parse `location_raw` into a structured `location_parsed` jsonb with `country`, `city`, `region`, `is_remote`. Use a small lookup table for the cities I care about.
- `src/policy_crawler/crawler/dedupe.py`:
  - Input: list of `JobRow` for a single source. Already deduped by `canonical_id` upstream; this layer adds **cross-source** dedupe by `(normalize_company_name(company), normalize_title(title), location_parsed.city)` hash. Mark duplicates by recording the first-seen `job_id` in a `duplicate_of` jsonb on the second.
- `src/policy_crawler/crawler/run.py`:
  - `crawl_all(only_kinds: set[FetcherKind] | None = None) -> RunSummary`:
    - Open a `runs` row with `kind = manual` (or whatever the caller passes).
    - For each enabled source: pick fetcher → `fetch()` → `normalize()` → upsert. Catch all exceptions per source; record into `runs.error` aggregate but never abort the whole run.
    - Update `sources.last_checked_at`; on success, `last_success_at`.
    - Upsert into `jobs` (match by `(source_id, canonical_id)`):
      - If new: insert; record `first_seen_at = now()`, `last_seen_at = now()`.
      - If exists and content changed (`title` / `location_raw` / `description_raw` hash differs): update job, append a `job_versions` row.
      - If exists and unchanged: just bump `last_seen_at`.
    - For sources where 0 jobs returned but the previous run returned >0, write a `WARNING` log and a `runs.warnings` entry.
    - Close the `runs` row with `status = succeeded` / `partial` / `failed`.

### CLI

- `python -m policy_crawler.crawler.run --kind manual` runs `crawl_all()` once.
- `python -m policy_crawler.crawler.run --source <name>` runs a single source for debugging.
- `python -m policy_crawler.crawler.run --configure-generic-html` walks every `generic_html` source and attempts `configure()` to suggest selectors interactively (prints to stdout; doesn't auto-write).

### Tests

- `tests/crawler/test_<each_fetcher>.py` — VCR cassette per fetcher against a real source. Greenhouse / Lever / Ashby fetchers must each have a recorded cassette + assertion that ≥ 1 `RawJob` is produced.
- `tests/crawler/test_normalize.py` — fixture `RawJob`s covering each posting type, asserting correct enum mapping.
- `tests/crawler/test_dedupe.py` — synthetic duplicates across two fake sources.
- `tests/crawler/test_run.py` — end-to-end against a sandboxed DB schema; uses fakes for fetchers; asserts idempotency on a second run (no new rows, no new versions).

## Acceptance criteria

```bash
pytest -q tests/crawler/

# Run end-to-end against the real seeded sources (with .env populated):
python -m policy_crawler.crawler.run --kind manual
# Expect: a non-trivial number of jobs in the jobs table after first run.

# Re-run immediately:
python -m policy_crawler.crawler.run --kind manual
# Expect: 0 new jobs created; last_seen_at bumped on existing rows.
```

```sql
SELECT s.name, count(j.*) AS jobs
FROM sources s LEFT JOIN jobs j ON j.source_id = s.id
WHERE s.enabled
GROUP BY s.name
ORDER BY 2 DESC LIMIT 20;
-- Expect: top sources have at least a handful of jobs each.
```

## Implementation notes

- **HTTP client**: a shared `httpx.Client` with `timeout=30`, `follow_redirects=True`, `User-Agent` set to a recognizable string (e.g., `policy-crawler/0.1 (+https://github.com/victorehrnrooth3/policy-crawler)`). Use `tenacity` with exponential backoff for 429/5xx.
- **Greenhouse content flag**: pass `content=true` to get full HTML descriptions. Some boards 404; handle gracefully.
- **Workday endpoint discovery is fragile.** Pattern: `https://<tenant>.myworkdayjobs.com/<site>/...`. The JSON endpoint is `POST https://<tenant>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs` with body `{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}`. Some tenants block the endpoint or use SAML — those should fall back to `generic_html` or `playwright`.
- **iCIMS** is intentionally not a separate fetcher in v1: most iCIMS pages are JS-rendered and the careful approach is to handle them via `playwright` per-source. Add an `icims` Tier-1 fetcher only if 3+ sources need it.
- **Don't trust ATS-reported `location`.** Always pass through `normalize.location_parsed` because some sources cram multiple cities into one string.
- **`canonical_id` for `generic_html`**: `sha1(absolute_url)`. If the page changes URL between runs (rare but happens), the job will appear "new" — that's acceptable; downstream dedupe usually catches it.
- **Idempotency** is non-negotiable: re-running on the same day must not create new jobs or new `job_versions` rows. Use `INSERT ... ON CONFLICT (source_id, canonical_id) DO UPDATE SET last_seen_at = excluded.last_seen_at`. Only insert into `job_versions` when a content hash differs.
- **No LLM calls in this step.** The "configure generic_html selectors interactively" CLI is human-driven; an LLM-assisted version can come later as a Followup.

## Out of scope

- LLM scoring (Step 05).
- Source discovery / suggested sources (Step 09).
- Rate-limit per-source overrides — defer until needed.

## Followups

- LLM-assisted `configure` for `generic_html`: feed the page HTML to Sonnet and ask it to propose selectors. Defer until the manual cost gets annoying.
- Add an `eventbrite_speaker` or LinkedIn-Jobs-RSS fetcher only if specific user-approved sources need them.
- Add per-source rate limits to `fetcher_config`.
