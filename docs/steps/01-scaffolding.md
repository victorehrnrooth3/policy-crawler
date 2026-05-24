# Step 01 — Scaffolding

## Goal

Stand up the empty Python project with package layout, dependency manifest, linter, formatter, and test runner so all later steps have a working development environment to drop code into.

## Reading list

- `docs/00-overview.md`
- `docs/01-architecture.md` (skim — you mostly need the project layout)
- `docs/03-tech-stack.md`
- `docs/04-conventions.md`

## Inputs / prereqs

- Local Python 3.12 install.
- Empty git repo (already initialized; remote points at `origin`).
- No accounts needed yet (no Neon / Anthropic / Vercel / Resend wired in this step).

## Deliverables

Create exactly these files, no more:

- `pyproject.toml` — `[project]` with name, version `0.1.0`, `requires-python = ">=3.12,<3.13"`, `[project.optional-dependencies]` with a `dev` extra. Pin top-level deps to compatible-release ranges (`~=`). Include at least:
  - Core: `httpx`, `selectolax`, `pydantic`, `pydantic-settings`, `python-dotenv`, `psycopg[binary,pool]`, `pyyaml`, `structlog`, `anthropic`, `jinja2`, `fastapi`, `uvicorn`, `resend`, `tenacity`.
  - Dev extras: `pytest`, `pytest-vcr`, `pytest-asyncio`, `ruff`, `pyright`, `freezegun`, `respx`.
  - Note: `playwright` is intentionally *not* in core; it'll be a separate optional extra (`[project.optional-dependencies].playwright`) so the default install stays small.
- `ruff.toml` — `target-version = "py312"`, `line-length = 100`, `lint.select = ["E", "F", "I", "B", "UP", "SIM", "C4", "RET", "PT"]`, plus a `[format]` section.
- `pyrightconfig.json` — non-strict, `include = ["src", "tests"]`, `pythonVersion = "3.12"`.
- `.env.example` — every secret listed in `docs/03-tech-stack.md` with placeholder values and a one-line comment per secret.
- `.gitignore` — Python standard plus `.env`, `.venv`, `.pytest_cache/`, `.ruff_cache/`, `node_modules/`, `.vercel/`, `*.cassette.yaml.bak`, `__pycache__/`, `.DS_Store`.
- `src/policy_crawler/__init__.py` — exports `__version__ = "0.1.0"`.
- `src/policy_crawler/config.py` — a `pydantic-settings` `Settings` class loading from env, with all the secrets from `03-tech-stack.md`. Provide a `get_settings()` cached factory.
- `src/policy_crawler/models.py` — empty stub (just `from __future__ import annotations` for now); subsequent steps will populate.
- `tests/__init__.py` and `tests/test_smoke.py` — single test asserting `__version__ == "0.1.0"` and that `get_settings()` works when env vars are set via monkeypatch.
- `README.md` — short description, link to `docs/00-overview.md` for the full story, install + test snippet.

## Acceptance criteria

Run these commands from the repo root and confirm they all succeed:

```bash
python -m venv .venv
. .venv/Scripts/activate           # PowerShell: .venv\Scripts\Activate.ps1
pip install -e .[dev]
ruff check .
ruff format --check .
pyright
pytest -q
```

All five must exit 0. If any fails, fix before declaring done.

## Implementation notes

- Do **not** create the `crawler/`, `ranker/`, `digest/`, `discovery/`, `self_update/`, `webapp/`, `obs/`, `migrations/`, `data/`, or `.github/workflows/` subtrees in this step. Later steps own those. (Empty placeholder folders cause noise in PRs.)
- `pydantic-settings` v2 syntax: `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`.
- For the `Settings` class, mark optional-in-dev-but-required-in-prod fields as `str | None = None` and validate at use site rather than at import. Otherwise `pytest` blows up because secrets aren't set.
- `psycopg[binary,pool]` chooses the binary wheel which avoids needing `libpq` on the dev machine. Production may switch to `psycopg[c]` later.
- Don't add a `Makefile`. Document common commands in `README.md` instead.
- Don't commit `uv.lock` / `requirements.txt` / `poetry.lock` — `pyproject.toml` is the source of truth.

## Out of scope

- Any database connection logic (Step 02).
- Any source registry data (Step 03).
- Any actual fetcher / ranker / digest / webapp / orchestration code (later steps).
- Any GitHub Actions workflows (Step 08).
- Any Vercel config (Step 07).
