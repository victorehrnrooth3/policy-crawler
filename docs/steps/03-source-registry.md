# Step 03 — Source Registry & Seed

## Goal

Define the `data/sources.yaml` schema, hand-curate a v1 seed list of ~80 high-priority sources spanning all the categories in `docs/02-personal-context.md`, and write a loader that idempotently upserts them into the `sources` table.

## Reading list

- `docs/00-overview.md`
- `docs/01-architecture.md` (§ "Data model" — `sources` table; § "Fetcher tiers")
- `docs/02-personal-context.md` (the high-priority think-tank table and the "Trusted sources to monitor" section)
- `docs/03-tech-stack.md`
- `docs/04-conventions.md`
- `docs/steps/02-database.md`

## Inputs / prereqs

- Step 02 complete; `sources` table exists in Neon.
- The committed `Top think tanks.xlsx` at the repo root (used as a reference; not parsed at runtime — the data has already been transcribed into `docs/02-personal-context.md`).

## Deliverables

- `data/sources.yaml` — the seed list, schema below.
- `src/policy_crawler/seed.py`:
  - `load_yaml(path)` returning a list of validated `SourceSeed` Pydantic models.
  - `upsert_sources(seeds)` that writes to the `sources` table:
    - Match by `(name, careers_url)` for upsert key.
    - Update `category`, `fetcher_kind`, `fetcher_config`, `geography_tags`, `priority`, `notes`, `homepage_url`, `enabled` (only if currently null).
    - Never overwrite `approved_by_me` (so a previously-rejected source doesn't get re-enabled by a re-seed).
  - A CLI: `python -m policy_crawler.seed --file data/sources.yaml --apply`.
- `tests/test_seed.py` — validates `data/sources.yaml` parses cleanly, and an end-to-end test (skipped without DB) that runs the upsert twice and asserts row count is stable on the second run.

## YAML schema

Top of file:

```yaml
# Schema version (bump when fields are added/removed)
version: 1
sources:
  - name: "Brookings Institution"
    homepage_url: "https://www.brookings.edu"
    careers_url: "https://www.brookings.edu/careers"
    category: think_tank
    fetcher_kind: generic_html        # set per real-world detection
    fetcher_config:
      list_selector: "..."            # required for generic_html / sitemap / rss
      title_selector: "..."           # ditto
      url_selector: "..."
      location_selector: "..."        # optional
    geography_tags: ["dc", "global"]
    priority: 5                       # 1 (low) .. 5 (high)
    enabled: true
    notes: "Domestic & economic policy. Multiple research divisions."
```

Required fields: `name`, `homepage_url`, `careers_url`, `category`, `fetcher_kind`, `geography_tags`, `priority`, `enabled`. `fetcher_config` is required when `fetcher_kind in {generic_html, sitemap, rss, workday_json, playwright}`; optional/empty otherwise.

## Initial seed (the agent must verify each careers URL returns 2xx before committing)

The agent should produce a `data/sources.yaml` with **at least the following sources** (and is encouraged to add a handful more if obvious during research). Set `priority = 5` for items marked high-priority below; `priority = 4` for the rest. **Mark `enabled: true` only after a successful 2xx check on `careers_url`** — if a URL is dead or has changed, set `enabled: false` and add a note.

Initial `fetcher_kind` may be a best guess; the actual detection happens in Step 04. Reasonable starting heuristics:
- URL contains `boards.greenhouse.io` or `boards-api.greenhouse.io` → `greenhouse`.
- URL contains `jobs.lever.co` → `lever`.
- URL contains `ashbyhq.com` or `jobs.ashbyhq.com` → `ashby`.
- URL contains `myworkdayjobs.com` → `workday_json`.
- URL contains `smartrecruiters.com` → `smartrecruiters`.
- Otherwise → `generic_html` with empty `fetcher_config: {}` (Step 04 will fill in selectors).

### Think tanks (priority 5 unless noted; geography tag based on HQ)

All 33 entries from the table in `docs/02-personal-context.md` § "Trusted sources to monitor (high-priority think tanks)". For each:
- `category: think_tank`
- `geography_tags`: HQ city tag (e.g., `dc`, `london`, `brussels`, `paris`, `berlin`, `geneva`, `nyc`, `boston`) plus `global` if international remit.
- `priority: 5` for: Brookings, CSIS, Chatham House, CFR, Atlantic Council, Belfer Center, IISS, RAND, RFF (added below), CGEP (added below), CSET (added below), TBI (added below), SIPRI, Bruegel, Carnegie Endowment, IFRI, PIIE, SWP, CEPR, Clingendael, LSE IDEAS, NUPI, Hudson, CNAS (added below).
- `priority: 4` for the rest.

Plus these additions not in the original spreadsheet but called out in `docs/02-personal-context.md`:
- **Resources for the Future (RFF)** — DC. `priority: 5`. `category: think_tank` AND a separate `predoc_program` entry for the RFF Predoctoral Fellowship page.
- **Center on Global Energy Policy at Columbia (CGEP)** — NYC.
- **Center for a New American Security (CNAS)** — DC.
- **Center for Security and Emerging Technology (CSET)** — DC. Plus a `predoc_program` entry for CSET Research Analyst.
- **Hudson Institute** — DC.
- **Royal United Services Institute (RUSI)** — London.
- **Tony Blair Institute (TBI)** — London. `priority: 5`.
- **Center for European Policy Analysis (CEPA)** — DC.
- **European Council on Foreign Relations (ECFR)** — Berlin / multi-city.
- **Mercator Institute for China Studies (MERICS)** — Berlin.
- **Center for Naval Analyses (CNA)** — Arlington VA.

### Asset-manager policy institutes (`asset_manager_policy_institute`, priority 5)

- BlackRock Investment Institute (NYC / London / Bay Area).
- KKR Global Institute (NYC).
- Carlyle Geopolitical Strategy / Carlyle Insight (DC / NYC).
- Apollo Strategic Research (NYC).
- Bridgewater Research (Westport CT / NYC).
- Goldman Sachs Global Investment Research — Geopolitical desk (NYC / London).

### Geopolitical-risk firms (`geopolitical_risk`, priority 5)

- Eurasia Group (NYC / DC / London / SF / Tokyo / São Paulo / Singapore).
- Rhodium Group (NYC / SF).
- Macro Advisory Partners (NYC / London).
- Control Risks (London / global).
- Teneo Risk Advisory (London / NYC).
- The Asia Group (DC).

### Corporate policy — frontier tech (`corporate_policy_tech`, priority 5)

- Anthropic — Policy team (SF / DC / London).
- OpenAI — Policy / Global Affairs (SF / DC / London).
- Google DeepMind — Policy (London / SF).
- Microsoft — Office of Responsible AI / AI policy (Redmond / DC / London).
- Meta — Policy (Menlo Park / DC / London).

### Corporate policy — defense tech (`corporate_policy_defense`, priority 5)

- Anduril — Strategy / Policy (Costa Mesa / DC).
- Palantir — Strategy & Communications (Denver / DC / London).
- Shield AI — Strategy (San Diego / DC).
- Saronic — Strategy (Austin).
- Lockheed Martin — Strategy (Bethesda).

### Corporate policy — energy (`corporate_policy_energy`, priority 5)

- NextEra Energy — Strategy (Juno Beach FL).
- Form Energy — Strategy (Boston).
- Commonwealth Fusion Systems — Strategy (Boston).
- Helion — Strategy (Everett WA).
- Equinor — New Energy / Strategy (Oslo / London).
- Shell — Scenarios team / Strategy (London / The Hague).
- BP — Strategy (London).

### IGOs / YPP-style (`igo`, priority 4–5)

- OECD (Paris) — careers + Young Professionals Programme.
- IEA (Paris) — careers.
- World Bank Group YPP (DC).
- IMF — Economist Program (DC).
- European Commission — EPSO (Brussels). Note: applications cycle is intermittent.
- NATO HQ (Brussels) and NATO Defense College (Rome).
- UNDP / UNEP / UN Department of Political and Peacebuilding Affairs (where they post research-relevant roles).

### Government (`government`, priority 4)

- US Federal Reserve Board RA Program (DC) — also a `predoc_program` entry.
- Federal Reserve Bank of New York / San Francisco / Boston / Chicago RA Programs.
- US Department of Energy — Loan Programs Office / Strategy (DC).
- UK Cabinet Office / No.10 Policy Unit (London).
- UK Foreign, Commonwealth & Development Office — Policy (London).
- Government of Finland — Prime Minister's Office strategy unit (Helsinki).

### Predoc / RA programs (`predoc_program`, priority 5)

- RFF Predoctoral Fellowship.
- Brookings Research Assistant program.
- CSET Research Analyst.
- BFI (Becker Friedman Institute, Chicago) Predoctoral Fellow.
- Federal Reserve Board RA (separate row).
- Stanford SIEPR Predoctoral Fellowship.
- MIT Sloan Predoctoral Fellow openings.

### PhD program calls (`phd_program`, priority 5)

The program-call entries listed in `docs/02-personal-context.md` § "Posting types of interest". For each, the source URL points to the program's PhD admissions page; the system will surface the application window opening as a "job" (Step 04 normalizer treats these as `posting_type: program_call`).

### Fellowships (`fellowship`, priority 5)

- Knight-Hennessy Scholars (Stanford).
- Schwarzman Scholars (Tsinghua).
- Marshall Scholarship.
- Rhodes Scholarship (Oxford).
- Mason Fellowship (Harvard PPOL).
- Belfer Center fellowships.
- TBI Future of Britain Fellowship.

## Acceptance criteria

```bash
# Lint the YAML
python -c "import yaml; yaml.safe_load(open('data/sources.yaml'))"

# Validate against Pydantic
python -m policy_crawler.seed --file data/sources.yaml --validate-only

# Apply (idempotent)
python -m policy_crawler.seed --file data/sources.yaml --apply
python -m policy_crawler.seed --file data/sources.yaml --apply  # second run: zero new rows
```

```sql
-- In Neon SQL editor:
SELECT category, count(*) FROM sources GROUP BY category ORDER BY 2 DESC;
-- Expect: think_tank ~40, then mix of others; total >= 80 rows.

SELECT count(*) FROM sources WHERE enabled = true;
-- Expect: most rows. Any disabled rows should have a note explaining why.
```

`pytest -q tests/test_seed.py` passes.

## Implementation notes

- **Verify URLs at seed time.** The agent should run a quick `httpx.head()` (with redirects) on each `careers_url`. If non-2xx, set `enabled: false` and add a `notes:` line. Don't fabricate URLs — if you can't find a real careers page for a given employer, omit that row and add a comment in the YAML.
- **Don't try to set perfect `fetcher_kind` values yet.** The detection in Step 04 will refine them. Use the URL-pattern heuristics above; default to `generic_html` for everything else and leave `fetcher_config: {}` empty. The fetcher framework in Step 04 will run a one-time "configure" pass that fills in selectors.
- **Geography tags are the source HQ, not job locations.** The crawler will populate per-job locations later. Source-level tags help the ranker prefer sources in my current geography window.
- **The PhD program-call entries** use `fetcher_kind: generic_html` against the program's "Apply" page. The fetcher recognizes "applications open" / "deadline" headers; if absent, it generates one synthetic posting per program per year with `posting_type: program_call`.
- The YAML file gets long (~80 rows × ~10 lines). Use anchors/aliases sparingly — keep it readable. Group sources by category with a leading comment per group.
- `Top think tanks.xlsx` stays in the repo as the original reference. The loader does not read it; the YAML is the source of truth.

## Out of scope

- Implementing actual fetchers (Step 04).
- LLM scoring (Step 05).
- A "suggested_sources" approval flow (Step 09).

## Followups

- Add per-source rate limits in `fetcher_config` once we observe real usage.
- Consider splitting `data/sources.yaml` into per-category files (`data/sources/think_tanks.yaml`, etc.) once it crosses ~150 rows.
