"""Ask Sonnet for a structured patch list against the preference profile.

The model returns a *diff* (a bounded list of add/remove/update ops with per-op
rationales), never a rewritten profile — so a bad suggestion changes one line, not
the whole file. Hard constraints (≤ 10 ops, no emptying must_haves/dealbreakers)
are stated in the prompt and re-enforced in code (here and in ``apply_diff``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import anthropic
import structlog
import yaml
from anthropic.types import Message, ToolParam
from pydantic import ValidationError

from policy_crawler.ranker.profile import Profile
from policy_crawler.self_update.apply_diff import PatchOp

logger = structlog.get_logger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2_048
_INPUT_PRICE_PER_1M = 3.00  # USD — Sonnet 4.6 input
_OUTPUT_PRICE_PER_1M = 15.00  # USD — Sonnet 4.6 output
_MAX_OPS = 10

SYSTEM_PROMPT = (
    "You maintain a user's job-preference profile. Given the current profile and a "
    "summary of the past week's feedback, propose a SMALL, conservative structured diff "
    "that nudges the profile toward what the feedback reveals. Rules you MUST follow:\n"
    "- Return at most 10 ops. Fewer is better. Zero ops is a valid, good answer if the "
    "week's feedback does not justify a change.\n"
    "- Never delete or empty `must_haves` or `dealbreakers` unless the feedback shows a "
    "clear, repeated pattern contradicting them.\n"
    "- Never touch `version` or `identity.cv_url`.\n"
    "- Prefer adding/refining topic keywords and soft_negatives over structural rewrites.\n"
    "- Every op needs a concrete `reason` grounded in the feedback summary.\n"
    "Use the `propose_profile_diff` tool — never reply in free-form text."
)

_PATCH_OP_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {"type": "string", "enum": ["add", "remove", "update"]},
        "path": {
            "type": "string",
            "description": (
                "Dotted path with optional [index] or [+] append, e.g. "
                "'topics.heavy[2].keywords', 'soft_negatives[+]', 'geography.timeline_note'."
            ),
        },
        "value": {
            "description": "New value (string, list, or object). Omit for remove ops.",
        },
        "reason": {"type": "string", "description": "Why this change, grounded in feedback."},
    },
    "required": ["op", "path", "reason"],
}

PROPOSE_DIFF_TOOL: ToolParam = {
    "name": "propose_profile_diff",
    "description": "Propose a structured diff to the user's preference profile.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ops": {"type": "array", "items": _PATCH_OP_SCHEMA, "maxItems": _MAX_OPS},
            "summary": {
                "type": "string",
                "description": "One-sentence summary of the proposed change set.",
            },
        },
        "required": ["ops", "summary"],
    },
}


@dataclass
class ProposedDiff:
    ops: list[PatchOp] = field(default_factory=list)
    summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * _INPUT_PRICE_PER_1M
            + self.output_tokens / 1_000_000 * _OUTPUT_PRICE_PER_1M
        )


def _extract_tool_input(message: Message) -> dict | None:
    for block in message.content:
        if block.type == "tool_use":
            return block.input  # type: ignore[return-value]
    return None


def _parse_ops(raw_ops: list) -> list[PatchOp]:
    ops: list[PatchOp] = []
    for raw in raw_ops:
        try:
            ops.append(PatchOp.model_validate(raw))
        except ValidationError as exc:
            logger.warning("self_update.propose.invalid_op", raw=raw, error=str(exc))
    return ops


def _build_prompt(profile: Profile, feedback_md: str) -> str:
    profile_yaml = yaml.safe_dump(profile.model_dump(), sort_keys=False, allow_unicode=True)
    return (
        f"## Current profile (data/profile.yaml)\n```yaml\n{profile_yaml}```\n\n"
        f"{feedback_md}\n\n"
        f"---\n\n"
        f"Propose a conservative diff using the `propose_profile_diff` tool. "
        f"At most {_MAX_OPS} ops; zero ops is fine if no change is warranted."
    )


def propose(
    profile: Profile,
    feedback_md: str,
    *,
    client: anthropic.Anthropic,
) -> ProposedDiff:
    """Call Sonnet once (with one stricter retry) for a profile diff."""
    prompt = _build_prompt(profile, feedback_md)
    result = ProposedDiff()

    for attempt in range(2):
        system = SYSTEM_PROMPT
        if attempt == 1:
            system += (
                "\n\nYour previous attempt returned an unusable number of ops. Return BETWEEN "
                f"0 AND {_MAX_OPS} ops. If unsure, return zero ops."
            )
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[PROPOSE_DIFF_TOOL],
                tool_choice={"type": "tool", "name": "propose_profile_diff"},
            )
        except Exception as exc:  # noqa: BLE001 - record + bail, never crash the weekly run
            result.error = f"sonnet: {exc}"
            logger.warning("self_update.propose.api_error", error=str(exc))
            return result

        result.input_tokens += response.usage.input_tokens
        result.output_tokens += response.usage.output_tokens

        tool_input = _extract_tool_input(response) or {}
        ops = _parse_ops(tool_input.get("ops") or [])
        result.summary = (tool_input.get("summary") or "").strip()

        if len(ops) <= _MAX_OPS:
            result.ops = ops
            logger.info(
                "self_update.propose.done",
                attempt=attempt,
                ops=len(ops),
                cost=round(result.cost_usd, 6),
            )
            return result
        logger.warning("self_update.propose.too_many_ops", attempt=attempt, ops=len(ops))

    # Both attempts over-produced — accept nothing rather than apply an unbounded diff.
    result.ops = []
    return result
