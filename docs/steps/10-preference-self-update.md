# Step 10 — Preference Self-Update

## Status

**Done** (functionally complete). The `self_update` package ships in
`step-09-source-config`. The weekly pipeline (`--kind weekly`) calls
`run_self_update` after discovery; the webapp `/profile` approve button calls
`apply_proposed`, which opens a PR via the GitHub REST API. See "As-built
departures" at the bottom for differences between this spec and what was built.

---

## Goal

Once a week, propose a structured diff to `data/profile.yaml` based on the past week's feedback, with a per-change rationale. Surface the diff for me to approve in the webapp. Apply the diff only on my approval, via a PR opened by the workflow.

## Reading list

- `docs/01-architecture.md` (§ "Preference self-update")
- `docs/02-personal-context.md`
- `docs/04-conventions.md`
- `docs/steps/05-preference-and-ranker.md` (the ranker that consumes the profile)
- `docs/steps/07-vote-endpoint-and-webapp.md` (the approval UI)
- `docs/steps/08-orchestration.md` (the weekly workflow)

## Inputs / prereqs

- Steps 01–09 complete; `feedback` table has rows.
- A fine-grained GitHub PAT scoped to this repo with `contents: write` and `pull_requests: write`, stored as `GH_PAT_FOR_PROFILE_PR`.

## Deliverables

- `src/policy_crawler/self_update/summarize_feedback.py`:
  - `summarize(window_days=7) -> FeedbackSummary` aggregating: count of votes by kind, top liked/disliked jobs with snippets, recurring themes in `freetext` (simple keyword frequency), geography hits/misses, posting-type distribution.
- `src/policy_crawler/self_update/propose_diff.py`:
  - `propose(profile: Profile, summary: FeedbackSummary) -> ProposedDiff`:
    - Sonnet 4.6 call with a tool-use schema. The schema is a structured **patch list**, not a free-form rewritten profile:
      ```python
      PATCH_OP = {
        "type": "object",
        "properties": {
          "op": {"type": "string", "enum": ["add", "remove", "update"]},
          "path": {"type": "string"},  # e.g., "topics.heavy[2]" or "must_haves[+]"
          "value": {},                  # context-specific
          "reason": {"type": "string"}
        },
        "required": ["op", "path", "reason"]
      }
      PROPOSE_DIFF_TOOL = {
        "name": "propose_profile_diff",
        "description": "Propose a structured diff to the user's preference profile.",
        "input_schema": {
          "type": "object",
          "properties": {
            "ops": {"type": "array", "items": PATCH_OP, "maxItems": 10},
            "summary": {"type": "string"}
          },
          "required": ["ops", "summary"]
        }
      }
      ```
    - The prompt includes: the **full** current `profile.yaml` (it's small), the FeedbackSummary, and a strong constraint: ≤ 10 ops total, no op deletes a `must_have` or `dealbreaker` without a corroborating pattern in the feedback (state this in the prompt and verify in code).
- `src/policy_crawler/self_update/apply_diff.py`:
  - `apply(profile: Profile, ops: list[PatchOp]) -> Profile` — pure function applying the patch list. Validate post-application against the Pydantic schema.
  - `apply_to_yaml(yaml_path, ops) -> str` — produces the new YAML text without re-formatting unrelated sections (use `ruamel.yaml` to preserve comments and ordering).
- `src/policy_crawler/self_update/run.py`:
  - `run_self_update(run_id)`:
    - Builds summary, calls `propose`, persists the proposed diff to `proposed_profile_changes`.
    - Does **not** apply the diff. Awaits webapp approval.
  - `apply_proposed(change_id, gh_pat)`:
    - Called by the webapp on approval (Step 07's `/profile/changes/{id}/approve`).
    - Reads the diff, applies to the working `data/profile.yaml`, opens a PR titled `chore: apply profile self-update YYYY-MM-DD` using `peter-evans/create-pull-request` semantics (or a small in-process git+gh shellout). Marks the row `applied`.
- Update Step 08's `weekly.yml` to invoke `python -m policy_crawler.self_update.run` after the discovery sub-job.
- `tests/self_update/test_*.py`:
  - `test_summarize.py` — given synthetic feedback rows, expected aggregations.
  - `test_propose.py` — mocked Sonnet response → schema-valid ops.
  - `test_apply_diff.py` — round-trip a YAML through a few op kinds; assert validation post-apply.
  - `test_run.py` — end-to-end with mocks.

## Acceptance criteria

```bash
# With synthetic feedback rows:
python -m policy_crawler.self_update.run
```

```sql
SELECT id, status, jsonb_pretty(diff), jsonb_pretty(rationale_per_change), proposed_at
FROM proposed_profile_changes
ORDER BY proposed_at DESC LIMIT 1;
-- Expect: a single pending row with 1-10 ops and clear per-op rationales.
```

In the webapp `/profile`:
- The proposed diff renders as a side-by-side or unified diff (whichever is easier).
- "Approve" creates a PR in the repo (visible in GitHub) and marks the change applied.
- "Reject" marks the change rejected with no PR.

## Implementation notes

- **`ruamel.yaml`** is required (not just `pyyaml`) to preserve comments + ordering when patching. Add to deps in this step.
- **Path syntax**: simple JSON-Pointer-like syntax. `topics.heavy[2].keywords` is OK; `must_haves[+]` means append. Document the syntax in `apply_diff.py` and validate strictly.
- **Guardrails**:
  - Reject any op that targets `version` or `identity.cv_url`.
  - Reject any op that empties `must_haves` or `dealbreakers`.
  - If the model proposes more than 10 ops or zero ops, retry once with a stricter system addition. Then accept zero (no-op weeks are fine).
- **Surfacing in the webapp**: render with the simpler representation (a list of ops with per-op rationales) plus a collapsible "full proposed YAML" view.
- **PR opening**: call `gh` CLI (preinstalled on `ubuntu-latest`) inside the action with `GITHUB_TOKEN: ${{ secrets.GH_PAT_FOR_PROFILE_PR }}`. PR body includes the rationale list and a checklist mirroring my approval clicks.
- **Post-merge effect**: on `main`, the next daily run will pick up the new `profile.yaml` automatically — no extra wiring needed.
- **Conflict between this and `02-personal-context.md`**: don't try to update `02-personal-context.md` from feedback. That doc is human-authored truth-about-me. The runtime `profile.yaml` is the derived artifact.

## Out of scope

- Auto-applying without my approval. Forbidden in v1 (and probably forever).
- Updating exemplars in the profile from feedback automatically — that happens in the prompt few-shot already (Step 5). Defer profile-level exemplar updates until they prove valuable.

## Followups

- Add a "drift report": measure cosine similarity between the past week's profile and the previous month's average; flag if drift > threshold for human review.
- A weekly digest email summarizing which proposed changes I accepted/rejected (auditing).
- **Side-by-side rendered diff in `/profile`**: the webapp currently shows the raw ops JSON + a rationale `<details>`. A proper old-vs-new YAML view (compute new text client- or server-side and diff it) is a UX nicety, not yet built.
- **Collapsible "full proposed YAML" view**: deferred for the same reason.

## As-built departures

The code is authoritative; this section explains the delta from the spec above.

**PR is opened via the GitHub REST API, not `peter-evans/create-pull-request` or a `gh` shellout.** The approve action runs in the webapp on Vercel's read-only, repo-less filesystem, where neither a checkout nor the `gh` CLI exists. `self_update/run.py:_open_profile_pr` instead calls `api.github.com` directly with `httpx` + the `GH_PAT_FOR_PROFILE_PR`: read `main`'s head sha, GET the current `data/profile.yaml`, apply the patch to *that* text (not the possibly-stale bundled copy), create a branch, commit, and open the PR. A new `GITHUB_REPOSITORY` setting (defaulting to `victorehrnrooth3/policy-crawler`) names the target repo.

**`apply_to_yaml` is split into `apply_to_yaml_text(text, ops)` + a thin path wrapper.** The text variant lets the webapp patch content fetched from GitHub without touching the filesystem; the weekly CLI path-based wrapper delegates to it.

**Guardrails live in the patch engine, enforced for both entry points.** `apply_diff.py` rejects ops touching `version` / `identity.cv_url` and any op that empties `must_haves` / `dealbreakers`, plus invalid paths / out-of-range indices. `run_self_update` dry-runs `apply(profile, ops)` before persisting, so a guardrail-violating diff is never queued.

**`run_self_update` skips the LLM call entirely on a zero-feedback week** (no `feedback` rows in the window) and inserts no `proposed_profile_changes` row when the model returns zero ops — both are valid no-op outcomes, not errors.

**No standalone `weekly.yml` step for self-update.** Per Step 08's as-built (single unified `--kind weekly`), self-update runs inside the one weekly invocation after discovery, not as a separate workflow step. The `weekly_self_update` `--kind` remains for ad-hoc CLI / `workflow_dispatch` use.

**Feedback summarization is heuristic, as specified**: vote tallies, liked/disliked job lists with free-text, posting-type mix, a light geography token scan, and stopword-filtered free-text theme frequency (threshold ≥ 2 occurrences).
