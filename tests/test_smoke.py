from __future__ import annotations

import pytest

from policy_crawler import __version__
from policy_crawler.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_get_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("NEON_DATABASE_URL", "postgresql://example/db")

    settings = get_settings()

    assert isinstance(settings, Settings)
    assert settings.anthropic_api_key == "test-anthropic-key"
    assert settings.neon_database_url == "postgresql://example/db"
