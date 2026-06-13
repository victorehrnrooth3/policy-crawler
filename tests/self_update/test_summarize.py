"""Tests for feedback summarization — DB I/O mocked."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from policy_crawler.self_update import summarize_feedback as sf


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        return None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeConn:
    def __init__(self, cur: _FakeCursor) -> None:
        self._cur = cur

    def cursor(self) -> _FakeCursor:
        return self._cur


def _wire(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> None:
    @contextmanager
    def fake_connection():
        yield _FakeConn(_FakeCursor(rows))

    monkeypatch.setattr(sf, "connection", fake_connection)


def test_empty_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, [])
    summary = sf.summarize(window_days=7)
    assert summary.is_empty
    assert summary.total == 0


def test_aggregations(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "vote": "up",
            "freetext": "love the energy policy angle here",
            "title": "Energy Analyst",
            "company": "RFF",
            "location_raw": "Washington DC",
            "posting_type": "role",
        },
        {
            "vote": "up",
            "freetext": "great energy focus",
            "title": "Research Associate",
            "company": "CGEP",
            "location_raw": "New York, NYC",
            "posting_type": "predoc",
        },
        {
            "vote": "down",
            "freetext": "too much pure finance",
            "title": "IB Analyst",
            "company": "GS",
            "location_raw": "London",
            "posting_type": "role",
        },
    ]
    _wire(monkeypatch, rows)
    summary = sf.summarize(window_days=7)

    assert summary.total == 3
    assert summary.by_vote == {"up": 2, "down": 1}
    assert len(summary.liked) == 2
    assert len(summary.disliked) == 1
    assert summary.posting_type_counts == {"role": 2, "predoc": 1}
    # "energy" appears in two free-text comments -> a theme (threshold >= 2)
    theme_words = {w for w, _ in summary.themes}
    assert "energy" in theme_words
    # geography tokens detected from location + freetext
    assert summary.geography_counts.get("dc") == 1
    assert summary.geography_counts.get("london") == 1


def test_to_prompt_is_nonempty(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "vote": "save",
            "freetext": "",
            "title": "Fellow",
            "company": "IISS",
            "location_raw": "London",
            "posting_type": "fellowship",
        }
    ]
    _wire(monkeypatch, rows)
    summary = sf.summarize()
    text = summary.to_prompt()
    assert "IISS" in text
    assert "Liked" in text
