# Agent Continuation Prompt — paste this verbatim into Claude Code / Cursor / etc.

Use this when you're picking up Step 02 from a personal / non-corporate machine. Paste the **quoted block below** into your agent's chat as a single message.

---

> You are continuing the **Policy Crawler** project from a fresh machine. The repo's previous session paused before executing Step 02 because the user's work laptop was behind a corporate egress filter that blocked Postgres traffic. We are now on a network with clean egress.
>
> Read these files in order, end-to-end, before writing any code:
>
> 1. `docs/STATUS.md`
> 2. `docs/handoffs/2026-05-24-step-02-database.md` (the full handoff — covers everything below, plus full session context)
> 3. `docs/00-overview.md`
> 4. `docs/01-architecture.md`
> 5. `docs/03-tech-stack.md`
> 6. `docs/04-conventions.md`
> 7. `docs/steps/02-database.md` (the target step)
> 8. `docs/steps/01-scaffolding.md` (skim — already complete)
>
> Then, before writing any Step 02 code:
>
> a) Confirm you're on the `step-02-database` branch and the working tree is clean (`git status`).
>
> b) Confirm `.env` exists at the repo root and both `NEON_DATABASE_URL` (pooled, host contains `-pooler.`) and `NEON_DATABASE_URL_DIRECT` (direct, no `-pooler.`) are populated. If `.env` is missing, copy `.env.example` to `.env` and paste both URLs from the Neon dashboard at neon.tech — the project is named `policy-crawler`, database is `neondb`, region is `aws-eu-central-1`.
>
> c) Set up the Python venv if it doesn't exist:
>    ```
>    python -m venv .venv
>    . .venv/Scripts/activate   # or source .venv/bin/activate on mac/linux
>    pip install -e .[dev]
>    ```
>
> d) Probe Neon connectivity before doing anything else. From the repo root, run:
>    ```
>    .\.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; import psycopg; load_dotenv(); psycopg.connect(os.environ['NEON_DATABASE_URL_DIRECT'], connect_timeout=30).close(); print('ok')"
>    ```
>    If it prints `ok`, proceed. If it prints `server closed the connection unexpectedly`, you are still behind a corporate filter — stop and tell the user to switch networks. Do not start writing Step 02 code if Neon is unreachable; the whole point of resuming on this machine is that we expected reachability.
>
> Once Neon is reachable, execute the **Step 02 plan inlined in `docs/handoffs/2026-05-24-step-02-database.md`** under § "Step 02 plan (inlined, ready to execute)". That section contains exact file contents, choices already made, and verification commands. Build only the deliverables listed in `docs/steps/02-database.md`'s "Deliverables" section. Verify the "Acceptance criteria" before declaring done.
>
> Conventions reminders:
> - Use Anthropic **tool-use** for any LLM call (not free-text JSON parsing). Not relevant for Step 02 but applies later.
> - Migrations use `NEON_DATABASE_URL_DIRECT`; the app pool uses `NEON_DATABASE_URL` (pooled). Do not mix.
> - `get_settings()` and `get_pool()` are both `@lru_cache` / `@cache`-d. Tests that mutate env or pool state must clear the cache (autouse fixture).
> - Run `ruff format .` once after writing/editing Python files, then `ruff format --check .` to verify.
> - All five acceptance commands (`pip install -e .[dev]`, `ruff check`, `ruff format --check`, `pyright`, `pytest -q`) must exit 0 before declaring Step 02 done.
> - Do not commit `.env`. Do not log secrets.
>
> If you find a contradiction between docs, stop and ask. Reference docs (`docs/01-architecture.md`, `docs/03-tech-stack.md`, `docs/04-conventions.md`) override step files; `docs/00-overview.md` overrides everything.
>
> When Step 02 is complete:
> - Update `docs/STATUS.md` to mark Step 02 done.
> - Commit with a `feat:` message (see suggested template in the handoff doc).
> - Push to `origin/step-02-database`.
> - Ask the user whether to open a PR or proceed to Step 03.

---

That's it. The handoff doc contains everything else (exact SQL, exact Python, verification queries, commit message template). The agent should not need to ask the user any setup questions — only domain decisions.
