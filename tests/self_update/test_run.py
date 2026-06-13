"""Tests for self-update orchestration — DB, LLM, and GitHub I/O mocked."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from policy_crawler.self_update import run as su
from policy_crawler.self_update.apply_diff import ApplyError, PatchOp
from policy_crawler.self_update.propose_diff import ProposedDiff
from policy_crawler.self_update.summarize_feedback import FeedbackItem, FeedbackSummary


def _summary(total: int) -> FeedbackSummary:
    s = FeedbackSummary(window_days=7, total=total)
    if total:
        s.liked = [FeedbackItem("up", "T", "C", "London", "role", "nice")]
    return s


def _diff(ops: list[PatchOp], error: str | None = None) -> ProposedDiff:
    return ProposedDiff(ops=ops, summary="s", input_tokens=400, output_tokens=80, error=error)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch):
    settings = MagicMock()
    settings.anthropic_api_key = "sk-test"
    monkeypatch.setattr(su, "get_settings", lambda: settings)
    monkeypatch.setattr(su, "load_profile", lambda: MagicMock())
    monkeypatch.setattr(su.anthropic, "Anthropic", lambda **k: MagicMock())
    monkeypatch.setattr(su, "_log_llm_call", lambda *a, **k: None)

    inserted: list[Any] = []
    monkeypatch.setattr(
        su,
        "_insert_proposed_change",
        lambda ops, summary, feedback: inserted.append((ops, summary)) or uuid4(),
    )
    monkeypatch.setattr(su, "apply", lambda profile, ops: MagicMock())  # diff-check passes
    return {"monkeypatch": monkeypatch, "inserted": inserted}


def test_no_feedback_skips(wired) -> None:
    wired["monkeypatch"].setattr(su, "summarize", lambda **k: _summary(0))
    summary = su.run_self_update()
    assert summary.ops_proposed == 0
    assert summary.change_id is None
    assert wired["inserted"] == []


def test_ops_proposed_inserts(wired) -> None:
    wired["monkeypatch"].setattr(su, "summarize", lambda **k: _summary(5))
    op = PatchOp(op="add", path="soft_negatives[+]", value="x", reason="r")
    wired["monkeypatch"].setattr(su, "propose", lambda *a, **k: _diff([op]))

    summary = su.run_self_update()

    assert summary.ops_proposed == 1
    assert summary.change_id is not None
    assert summary.cost_usd > 0
    assert len(wired["inserted"]) == 1


def test_zero_ops_no_insert(wired) -> None:
    wired["monkeypatch"].setattr(su, "summarize", lambda **k: _summary(5))
    wired["monkeypatch"].setattr(su, "propose", lambda *a, **k: _diff([]))
    summary = su.run_self_update()
    assert summary.ops_proposed == 0
    assert wired["inserted"] == []


def test_propose_error_no_insert(wired) -> None:
    wired["monkeypatch"].setattr(su, "summarize", lambda **k: _summary(5))
    wired["monkeypatch"].setattr(su, "propose", lambda *a, **k: _diff([], error="sonnet: boom"))
    summary = su.run_self_update()
    assert summary.errors
    assert wired["inserted"] == []


def test_apply_check_failure_no_insert(wired) -> None:
    wired["monkeypatch"].setattr(su, "summarize", lambda **k: _summary(5))
    op = PatchOp(op="remove", path="dealbreakers[0]", reason="r")
    wired["monkeypatch"].setattr(su, "propose", lambda *a, **k: _diff([op]))

    def boom(profile, ops):
        raise ApplyError("would empty dealbreakers")

    wired["monkeypatch"].setattr(su, "apply", boom)

    summary = su.run_self_update()
    assert summary.errors
    assert wired["inserted"] == []


# ── apply_proposed (approval path) ──────────────────────────────────────────


class _Cur:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row
        self.executed: list[tuple[Any, ...]] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, cur: _Cur) -> None:
        self._cur = cur

    def cursor(self):
        return self._cur


def _wire_change(monkeypatch: pytest.MonkeyPatch, row: dict[str, Any] | None):
    cur = _Cur(row)

    @contextmanager
    def fake_connection():
        yield _Conn(cur)

    monkeypatch.setattr(su, "connection", fake_connection)
    writes: list[Any] = []

    def fake_execute_write(work):
        wcur = _Cur(None)
        work(_Conn(wcur))
        writes.append(wcur.executed)

    monkeypatch.setattr(su, "execute_write", fake_execute_write)
    return writes


def test_apply_proposed_opens_pr_and_marks_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    cid = uuid4()
    row = {
        "id": cid,
        "status": "pending",
        "diff": {
            "ops": [{"op": "add", "path": "soft_negatives[+]", "value": "x", "reason": "r"}],
            "summary": "s",
        },
    }
    writes = _wire_change(monkeypatch, row)
    monkeypatch.setattr(su, "_open_profile_pr", lambda ops, summary, change_id, pat: "https://pr")

    url = su.apply_proposed(cid, "ghp_token")

    assert url == "https://pr"
    assert any("UPDATE proposed_profile_changes" in w[0][0] for w in writes)


def test_apply_proposed_missing_pat_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    cid = uuid4()
    row = {
        "id": cid,
        "status": "pending",
        "diff": {"ops": [{"op": "add", "path": "soft_negatives[+]", "value": "x", "reason": "r"}]},
    }
    _wire_change(monkeypatch, row)
    with pytest.raises(ApplyError):
        su.apply_proposed(cid, None)


def test_apply_proposed_not_pending_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    cid = uuid4()
    _wire_change(monkeypatch, {"id": cid, "status": "applied", "diff": {"ops": []}})
    with pytest.raises(ApplyError):
        su.apply_proposed(cid, "ghp_token")


def test_apply_proposed_unknown_change_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_change(monkeypatch, None)
    with pytest.raises(ApplyError):
        su.apply_proposed(uuid4(), "ghp_token")
