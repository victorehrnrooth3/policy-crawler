"""Application settings loaded from environment variables.

All secrets default to ``None`` so importing this module never fails in test or
CI environments. Validate required values at use-site (e.g. inside the digest
sender, the DB module) rather than at import time — otherwise unrelated tests
break the moment a single secret is missing.

See ``docs/03-tech-stack.md`` for the canonical list of secrets and where each
one lives in production.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view of every environment variable the system reads."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    neon_database_url: str | None = Field(default=None, alias="NEON_DATABASE_URL")
    neon_database_url_direct: str | None = Field(default=None, alias="NEON_DATABASE_URL_DIRECT")
    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")
    digest_from_email: str | None = Field(default=None, alias="DIGEST_FROM_EMAIL")
    digest_to_email: str | None = Field(default=None, alias="DIGEST_TO_EMAIL")
    webapp_base_url: str | None = Field(default=None, alias="WEBAPP_BASE_URL")
    token_hmac_secret: str | None = Field(default=None, alias="TOKEN_HMAC_SECRET")
    session_cookie_secret: str | None = Field(default=None, alias="SESSION_COOKIE_SECRET")
    gh_pat_for_profile_pr: str | None = Field(default=None, alias="GH_PAT_FOR_PROFILE_PR")
    # owner/repo target for the weekly profile self-update PR. GitHub Actions sets
    # GITHUB_REPOSITORY automatically; set it explicitly as a Vercel env var so the
    # webapp's approve route can open the PR too.
    github_repository: str = Field(
        default="victorehrnrooth3/policy-crawler", alias="GITHUB_REPOSITORY"
    )
    ranker_degrade_to_haiku_only: bool = Field(default=False, alias="RANKER_DEGRADE_TO_HAIKU_ONLY")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide ``Settings`` instance.

    Cached so repeated callers share one object. Tests that mutate the
    environment should call ``get_settings.cache_clear()`` between cases.
    """

    return Settings()
