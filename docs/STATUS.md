# Project Status

Single source of truth for "where are we right now?". Update this file at the end of every meaningful session.

## Snapshot (last updated: 2026-05-24, evening, London)

| Step | State | Branch | Notes |
|---|---|---|---|
| 01 — Scaffolding | **Done, committed, pushed** | `step-01-scaffolding` (`1587dac`) | All 5 acceptance commands exit 0. Audited and verified. |
| 02 — Database | **Planned, build paused** | `step-02-database` (this branch) | Blocked by corporate egress filter on the work laptop. Pick up on personal laptop. |
| 03–11 | Not started | — | — |

## Active blocker

Postgres traffic from the work laptop to Neon (`*.aws.neon.tech:5432`) is blocked by a corporate egress filter — TCP accepts, then the proxy resets the connection mid-handshake. This affects only the local migration apply + the live DB smoke test. Everything else (code authoring, ruff, pyright, pytest with the live test skipped, GitHub Actions CI later) is unaffected.

See [`docs/handoffs/2026-05-24-step-02-database.md`](handoffs/2026-05-24-step-02-database.md) for the diagnostic detail and three suggested workarounds (mobile tether, home wifi, defer-to-CI).

## What's on disk right now (this branch)

- Everything from `step-01-scaffolding`: `pyproject.toml`, `ruff.toml`, `pyrightconfig.json`, `.env.example`, `src/policy_crawler/{__init__,config,models}.py`, `tests/{__init__,test_smoke}.py`, README install/test section, two gotchas appended to `docs/04-conventions.md`.
- This branch adds **handoff documentation only**, no Step 02 code yet:
  - `docs/STATUS.md` — this file.
  - `docs/handoffs/2026-05-24-step-02-database.md` — full handoff: session summary + Step 02 plan + diagnostic findings + next-actions checklist.
  - `docs/handoffs/AGENT-CONTINUATION-PROMPT.md` — paste-able preamble for whatever agent continues from a non-corporate network.

## Next concrete actions (in order)

1. On a personal machine / mobile-tethered network, clone or pull `step-02-database`.
2. Re-create `.env` from `.env.example`, paste both Neon URLs (the work-laptop `.env` is gitignored and not on the new machine).
3. Open `docs/handoffs/AGENT-CONTINUATION-PROMPT.md`, paste its contents to the agent (Claude Code in VS Code, Cursor, or whatever you're using).
4. Agent verifies Neon connectivity, then executes the Step 02 plan inlined in `docs/handoffs/2026-05-24-step-02-database.md`.
5. After Step 02 lands and is verified, update this `STATUS.md` and start Step 03.

## Conventions reminder

When kicking off any step, follow the agent preamble in [`docs/04-conventions.md`](04-conventions.md) §"Agent-prompting conventions": read 00, 01, 03, 04 end-to-end, skim 02 if the step touches preferences/ranker/sources, then the target step file, then prior step files. Reference docs (01–04) override step files; the overview overrides everything.
