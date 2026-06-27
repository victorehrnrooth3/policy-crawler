"""Tests for obs/cost.py — pure pricing + DB-backed spend sums (connection mocked)."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from typing import Any
from uuid import uuid4

import pytest

from policy_crawler.obs import cost

# ── compute_call_cost (pure) ──────────────────────────────────────────────────


def test_compute_call_cost_sonnet() -> None:
    # $3/M input + $15/M output
    assert cost.compute_call_cost("claude-sonnet-4-6", 1_000_000, 1_000_000) == pytest.approx(18.0)


def test_compute_call_cost_haiku_dated_id_resolves_by_prefix() -> None:
    # Dated id must resolve to the base "claude-haiku-4-5" price entry.
    assert cost.compute_call_cost("claude-haiku-4-5-20251001", 1_000_000, 0) == pytest.approx(1.0)


def test_compute_call_cost_unknown_model_is_zero() -> None:
    assert cost.compute_call_cost("gpt-4o", 1_000_000, 1_000_000) == 0.0


# ── spend sums + degrade (DB mocked) ──────────────────────────────────────────


class _Cur:
    def __init__(self, value: Any) -> None:
        self._value = value
        self.last_sql: str = ""

    def __enter__(self) -> _Cur:
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.last_sql = sql

    def fetchone(self) -> dict[str, Any]:
        return self._value


class _Conn:
    def __init__(self, cur: _Cur) -> None:
        self._cur = cur

    def cursor(self) -> _Cur:
        return self._cur


def _patch_conn(monkeypatch: pytest.MonkeyPatch, value: Any) -> _Cur:
    cur = _Cur(value)

    @contextmanager
    def fake_connection() -> Generator[_Conn, None, None]:
        yield _Conn(cur)

    monkeypatch.setattr(cost, "connection", fake_connection)
    return cur


def test_daily_spend_sums(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_conn(monkeypatch, {"total": 0.1234})
    assert cost.daily_spend(date(2026, 6, 14)) == pytest.approx(0.1234)


def test_monthly_spend_sums(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_conn(monkeypatch, {"total": 3.5})
    assert cost.monthly_spend(date(2026, 6, 1)) == pytest.approx(3.5)


def test_run_spend_sums(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_conn(monkeypatch, {"total": 0.02})
    assert cost.run_spend(uuid4()) == pytest.approx(0.02)


def test_run_call_count(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_conn(monkeypatch, {"n": 7})
    assert cost.run_call_count(uuid4()) == 7


def test_should_degrade_below_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from policy_crawler.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DAILY_SOFT_CAP_USD", "0.30")
    _patch_conn(monkeypatch, {"total": 0.10})
    assert cost.should_degrade_to_haiku(date(2026, 6, 14)) is False
    get_settings.cache_clear()


def test_should_degrade_at_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from policy_crawler.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DAILY_SOFT_CAP_USD", "0.30")
    _patch_conn(monkeypatch, {"total": 0.30})  # >= cap triggers degrade
    assert cost.should_degrade_to_haiku(date(2026, 6, 14)) is True
    get_settings.cache_clear()
