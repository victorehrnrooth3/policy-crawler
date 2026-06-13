"""Tests for weekly source discovery — DB and LLM I/O are mocked.

Covers the parts unique to discovery: dedupe against existing sources/pending
suggestions, the camoufox fallback when no ATS is detected, skipping unreachable
URLs, and that candidates are queued (never auto-added) in suggested_sources.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from policy_crawler.crawler.detect import AtsDetection
from policy_crawler.discovery import run as disc


class _FakeCursor:
    """Cursor that returns queued fetchall results in order and records executes."""

    def __init__(self, fetch_results: list[list[dict[str, Any]]]) -> None:
        self._fetch_results = list(fetch_results)
        self.executed: list[tuple[Any, ...]] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))

    def fetchall(self) -> list[dict[str, Any]]:
        return self._fetch_results.pop(0)


class _FakeConn:
    def __init__(self, cur: _FakeCursor) -> None:
        self._cur = cur

    def cursor(self) -> _FakeCursor:
        return self._cur


def _mock_suggest_response(candidates: list[dict[str, Any]]) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"candidates": candidates}
    usage = MagicMock(input_tokens=800, output_tokens=300)
    msg = MagicMock()
    msg.content = [block]
    msg.usage = usage
    return msg


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch):
    """Wire up discovery with fakes; return a dict the test customizes/inspects."""
    settings = MagicMock()
    settings.anthropic_api_key = "sk-test"
    monkeypatch.setattr(disc, "get_settings", lambda: settings)
    monkeypatch.setattr(disc, "_log_llm_call", lambda *a, **k: None)
    monkeypatch.setattr(disc, "profile_for_prompt", lambda p: "PROFILE")
    monkeypatch.setattr(disc, "load_profile", lambda: MagicMock())

    # Read cursor: [recent_votes, existing_sources, pending_suggestions]
    read_cur = _FakeCursor(
        [
            [],  # recent feedback
            [{"name": "Anthropic"}],  # existing sources
            [{"name": "Old Pending", "careers_url": "https://pending.org/jobs"}],  # pending
        ]
    )

    @contextmanager
    def fake_connection():
        yield _FakeConn(read_cur)

    monkeypatch.setattr(disc, "connection", fake_connection)

    inserted: list[tuple[Any, ...]] = []

    def fake_execute_write(work):
        write_cur = _FakeCursor([])
        work(_FakeConn(write_cur))
        inserted.extend(write_cur.executed)

    monkeypatch.setattr(disc, "execute_write", fake_execute_write)

    client = MagicMock()
    monkeypatch.setattr(disc.anthropic, "Anthropic", lambda **k: client)

    return {"client": client, "inserted": inserted, "monkeypatch": monkeypatch}


def test_detected_ats_uses_its_kind(wired) -> None:
    wired["client"].messages.create.return_value = _mock_suggest_response(
        [
            {
                "name": "RFF",
                "careers_url": "https://rff.org/jobs",
                "category": "think_tank",
                "rationale": "fits",
            }
        ]
    )
    wired["monkeypatch"].setattr(
        disc, "detect_ats", lambda url: AtsDetection(kind="greenhouse", config={"board": "rff"})
    )

    summary = disc.run_discovery()

    assert summary.suggestions_inserted == 1
    # fetcher_kind (4th positional param in the insert tuple) is the detected ATS
    row_params = wired["inserted"][0][1]
    assert row_params[3] == "greenhouse"


def test_undetected_falls_back_to_camoufox(wired) -> None:
    wired["client"].messages.create.return_value = _mock_suggest_response(
        [
            {
                "name": "Some Think Tank",
                "careers_url": "https://stt.org/careers",
                "category": "think_tank",
                "rationale": "x",
            }
        ]
    )
    wired["monkeypatch"].setattr(disc, "detect_ats", lambda url: AtsDetection(kind="generic_html"))

    summary = disc.run_discovery()

    assert summary.suggestions_inserted == 1
    assert wired["inserted"][0][1][3] == "camoufox"


def test_skips_duplicate_of_existing_source(wired) -> None:
    wired["client"].messages.create.return_value = _mock_suggest_response(
        [
            {
                "name": "Anthropic",
                "careers_url": "https://anthropic.com/jobs",
                "category": "corporate_policy_tech",
                "rationale": "dup",
            }
        ]
    )
    wired["monkeypatch"].setattr(disc, "detect_ats", lambda url: AtsDetection(kind="greenhouse"))

    summary = disc.run_discovery()

    assert summary.suggestions_inserted == 0
    assert summary.skipped_duplicate == 1
    assert wired["inserted"] == []


def test_skips_unreachable_url(wired) -> None:
    wired["client"].messages.create.return_value = _mock_suggest_response(
        [
            {
                "name": "Dead Org",
                "careers_url": "https://dead.org/jobs",
                "category": "think_tank",
                "rationale": "x",
            }
        ]
    )
    wired["monkeypatch"].setattr(
        disc, "detect_ats", lambda url: AtsDetection(kind="unknown", evidence="fetch_error")
    )

    summary = disc.run_discovery()

    assert summary.suggestions_inserted == 0
    assert summary.skipped_unreachable == 1
