# Step 06 — Email Digest

## Goal

Build the daily email digest: pick the right jobs, render an HTML+text email with one-click vote links, and send it via Resend.

## Reading list

- `docs/01-architecture.md` (§ "Email digest", § "Vote endpoint + review webapp" — Step 07 owns the receiver but you need to know the URL shape)
- `docs/03-tech-stack.md` (Resend; secrets list)
- `docs/04-conventions.md`
- `docs/steps/05-preference-and-ranker.md`

## Inputs / prereqs

- Step 05 complete; jobs have `pass1_score` and (sometimes) `pass2_score`.
- Resend account set up; sending domain verified or using the default Resend `onboarding@resend.dev` for testing.
- Secrets present: `RESEND_API_KEY`, `DIGEST_FROM_EMAIL`, `DIGEST_TO_EMAIL`, `WEBAPP_BASE_URL`, `TOKEN_HMAC_SECRET`.

## Deliverables

- `src/policy_crawler/digest/tokens.py`:
  - `make_token(payload: dict, kind: str, expires_in: timedelta) -> str` — base64url(payload || HMAC-SHA256). Payload includes `job_id`, `vote` (when applicable), `iat`, `exp`, `nonce` (for single-use), `kind`.
  - `verify_token(token: str, expected_kind: str) -> dict | None` — verifies HMAC, expiry, expected kind. Single-use enforcement happens at the DB layer in Step 07 (a `consumed_tokens` table or a `feedback.token_nonce` unique column).
- `src/policy_crawler/digest/compose.py`:
  - `pick_jobs(today: date, k_top=8, k_borderline=2) -> list[JobRow]`:
    - Eligible: `digest_sent_at IS NULL` AND `pass1_score IS NOT NULL` AND not closed.
    - Top: highest `pass2_score` (falls back to `pass1_score` for jobs that didn't get a Pass 2). Up to `k_top`.
    - Borderline: jobs with `pass1_confidence = 'low'` and `pass1_score` in [40, 60]. Up to `k_borderline`. Helps surface things the system is unsure about so I can train it.
    - Filter out anything where `pass1_dealbreaker_hits` is non-empty unless `posting_type = 'program_call'` (program calls can have soft mismatches but still be worth knowing).
  - `mark_digest_sent(job_ids)` — bulk update `digest_sent_at = now()` and write a `runs.metadata.digest = {...}` entry.
- `src/policy_crawler/digest/template.py`:
  - Jinja2 templates `templates/digest.html.j2` and `templates/digest.txt.j2`. Subject line: `"[N] policy roles for {{ today.strftime('%a %d %b') }}"`.
  - Each card: title (linked to source), company, location, posting type, `pass2_score` (or `pass1_score` if no pass 2) with a small bar, two-sentence reason, three vote links (👍 / 👎 / 🔖) and a "deeper review" link to the webapp. Use plain markup; no JS, no remote images.
  - "Deeper review" link uses a session-establishing magic-link token (longer-lived) that lands on `/inbox`.
- `src/policy_crawler/digest/send.py`:
  - `send_digest(today: date | None = None, dry_run=False)`:
    - Calls `pick_jobs` → renders HTML + text → `resend.Emails.send(...)`.
    - On `dry_run=True`, writes the rendered HTML to `./out/digest-{today}.html` instead.
    - On real send, calls `mark_digest_sent`.
  - CLI: `python -m policy_crawler.digest --send` and `--dry-run`.
- `tests/digest/test_tokens.py` — round-trip, expiry, tampering rejection.
- `tests/digest/test_compose.py` — selection logic with synthetic jobs.
- `tests/digest/test_template.py` — snapshot test of HTML + text output.

## Acceptance criteria

```bash
pytest -q tests/digest/

# Dry run, render to file:
python -m policy_crawler.digest --dry-run
# Open out/digest-YYYY-MM-DD.html in a browser; eyeball the layout.

# Real send to my own address:
python -m policy_crawler.digest --send
# Confirm receipt; click a vote link (will 404 until Step 07 is deployed — acceptance for this step is just the email arrives correctly).
```

## Implementation notes

- **HMAC token format**: `urlsafe_b64encode(payload_json) + '.' + urlsafe_b64encode(hmac_sha256(key, payload_json))`. Payload is JSON for easy debugging.
- **Token expiry**: vote tokens 14 days; magic-link session tokens 30 days.
- **Single-use** enforcement is intentionally pushed to Step 07 because that's where the DB write happens. This step just produces tokens.
- **Vote URL shape**: `{WEBAPP_BASE_URL}/v/up/{token}`, `/v/down/{token}`, `/v/save/{token}`. Magic link: `{WEBAPP_BASE_URL}/m/{token}` (sets cookie, redirects to `/inbox`).
- **Don't put scores in the subject line.** Variability is annoying. Just the count of jobs and the date.
- **Dark-mode-safe HTML**: avoid hard-coded colors; use system defaults. Test in Gmail and the iOS Mail app at minimum.
- **Resend SDK**: `resend.api_key = ...` then `resend.Emails.send({"from": ..., "to": ..., "subject": ..., "html": ..., "text": ...})`. Handle the API returning a structured error and log it; don't raise.
- **Empty digest case**: if `pick_jobs` returns 0, send a tiny "no new jobs today" email instead of skipping. Helps confirm the pipeline is alive.
- **Rate limit**: Resend free tier is 100/day; we'll send 1/day. No batching needed.

## Out of scope

- The vote-receiving endpoint and the deeper-review webapp (Step 07).
- The orchestration cron (Step 08).
- Failure-alert emails (Step 11).

## Followups

- A "this week" weekly summary email separate from the daily digest.
- Adding a small "training corner" section that shows one borderline job per day with both options ("would surfacing more like this be valuable?") explicitly framed as feedback.
