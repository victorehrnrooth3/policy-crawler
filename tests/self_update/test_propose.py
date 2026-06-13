"""Tests for the Sonnet diff-proposer — anthropic client mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

from policy_crawler.ranker.profile import load_profile
from policy_crawler.self_update import propose_diff as pd


def _response(
    ops: list[dict], summary: str = "s", in_tok: int = 500, out_tok: int = 100
) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"ops": ops, "summary": summary}
    msg = MagicMock()
    msg.content = [block]
    msg.usage = MagicMock(input_tokens=in_tok, output_tokens=out_tok)
    return msg


def _client(*responses: MagicMock) -> MagicMock:
    client = MagicMock()
    client.messages.create.side_effect = list(responses)
    return client


def test_valid_ops_parsed() -> None:
    client = _client(
        _response(
            [
                {
                    "op": "add",
                    "path": "soft_negatives[+]",
                    "value": "too junior",
                    "reason": "repeated downvotes on junior roles",
                }
            ]
        )
    )
    diff = pd.propose(load_profile(), "FEEDBACK", client=client)

    assert len(diff.ops) == 1
    assert diff.ops[0].op == "add"
    assert diff.ops[0].path == "soft_negatives[+]"
    assert diff.error is None
    assert diff.cost_usd > 0
    assert client.messages.create.call_count == 1


def test_zero_ops_is_accepted() -> None:
    client = _client(_response([], summary="no change warranted"))
    diff = pd.propose(load_profile(), "FEEDBACK", client=client)
    assert diff.ops == []
    assert client.messages.create.call_count == 1


def test_invalid_op_dropped() -> None:
    client = _client(
        _response(
            [
                {"op": "frobnicate", "path": "x", "reason": "bad enum"},  # invalid -> dropped
                {"op": "update", "path": "geography.timeline_note", "value": "x", "reason": "ok"},
            ]
        )
    )
    diff = pd.propose(load_profile(), "FEEDBACK", client=client)
    assert len(diff.ops) == 1
    assert diff.ops[0].op == "update"


def test_too_many_ops_retries_then_empties() -> None:
    too_many = [
        {"op": "add", "path": "soft_negatives[+]", "value": str(i), "reason": "r"}
        for i in range(pd._MAX_OPS + 3)
    ]
    client = _client(_response(too_many), _response(too_many))
    diff = pd.propose(load_profile(), "FEEDBACK", client=client)

    assert client.messages.create.call_count == 2  # retried once
    assert diff.ops == []  # both over-produced -> accept nothing
    # tokens accumulate across both attempts
    assert diff.input_tokens == 1000


def test_api_error_recorded() -> None:
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    diff = pd.propose(load_profile(), "FEEDBACK", client=client)
    assert diff.error is not None
    assert "boom" in diff.error
    assert diff.ops == []
