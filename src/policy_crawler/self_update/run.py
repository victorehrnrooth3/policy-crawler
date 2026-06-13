"""Weekly preference self-update orchestration (Step 10).

``run_self_update`` (weekly job) summarizes feedback, asks Sonnet for a diff,
verifies the diff applies cleanly, and queues it in ``proposed_profile_changes``
for human review. It never edits the profile.

``apply_proposed`` (called by the webapp on approval) patches ``data/profile.yaml``
and opens a PR via the GitHub REST API — chosen over a git shellout because the
webapp runs on Vercel's read-only, repo-less filesystem. The change row is marked
``applied`` only after the PR is open.
"""

from __future__ import annotations

import base64
import contextlib
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

import anthropic
import httpx
import structlog

from policy_crawler.config import get_settings
from policy_crawler.db import connection, execute_write
from policy_crawler.ranker.profile import load_profile
from policy_crawler.self_update.apply_diff import ApplyError, PatchOp, apply, apply_to_yaml_text
from policy_crawler.self_update.propose_diff import _MODEL, propose
from policy_crawler.self_update.summarize_feedback import summarize, summary_to_jsonable

logger = structlog.get_logger(__name__)

_WINDOW_DAYS = 7
_PROFILE_REPO_PATH = "data/profile.yaml"
_GITHUB_API = "https://api.github.com"

_INSERT_CHANGE = """
INSERT INTO proposed_profile_changes (diff, rationale_per_change, status)
VALUES (%s::jsonb, %s::jsonb, 'pending')
RETURNING id
"""

_INSERT_LLM_CALL = """
INSERT INTO llm_calls (run_id, kind, model, input_tokens, output_tokens, cost_usd, error)
VALUES (%s, 'self_update', %s, %s, %s, %s, %s)
"""

_SELECT_CHANGE = "SELECT id, diff, status FROM proposed_profile_changes WHERE id = %s"


@dataclass
class SelfUpdateSummary:
    feedback_total: int = 0
    ops_proposed: int = 0
    change_id: str | None = None
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


# ── Weekly proposal job ───────────────────────────────────────────────────────


def run_self_update(
    run_id: UUID | None = None, *, window_days: int = _WINDOW_DAYS
) -> SelfUpdateSummary:
    """Summarize feedback, propose a profile diff, queue it for approval."""
    summary = SelfUpdateSummary()

    feedback = summarize(window_days=window_days)
    summary.feedback_total = feedback.total
    if feedback.is_empty:
        logger.info("self_update.skip.no_feedback", window_days=window_days)
        return summary

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    profile = load_profile()
    diff = propose(profile, feedback.to_prompt(), client=client)
    summary.cost_usd = diff.cost_usd
    _log_llm_call(run_id, diff.input_tokens, diff.output_tokens, diff.error)

    if diff.error:
        summary.errors.append(diff.error)
        return summary

    if not diff.ops:
        logger.info("self_update.no_change", summary=diff.summary)
        return summary

    # Verify the diff is structurally sound + passes guardrails before persisting.
    try:
        apply(profile, diff.ops)
    except ApplyError as exc:
        summary.errors.append(f"apply_check: {exc}")
        logger.warning("self_update.diff_rejected", error=str(exc))
        return summary

    change_id = _insert_proposed_change(diff.ops, diff.summary, summary_to_jsonable(feedback))
    summary.ops_proposed = len(diff.ops)
    summary.change_id = str(change_id)
    logger.info("self_update.queued", change_id=str(change_id), ops=len(diff.ops))
    return summary


def _insert_proposed_change(
    ops: list[PatchOp], change_summary: str, feedback_summary: dict[str, Any]
) -> UUID:
    diff_json = json_dumps({"ops": [op.model_dump() for op in ops], "summary": change_summary})
    rationale_json = json_dumps(
        {
            "feedback_summary": feedback_summary,
            "per_op": [{"op": op.op, "path": op.path, "reason": op.reason} for op in ops],
        }
    )

    captured: dict[str, UUID] = {}

    def work(conn: Any) -> None:
        with conn.cursor() as cur:
            cur.execute(_INSERT_CHANGE, (diff_json, rationale_json))
            captured["id"] = cur.fetchone()["id"]

    execute_write(work)
    return captured["id"]


# ── Approval / PR job (called by the webapp) ────────────────────────────────────


def apply_proposed(change_id: UUID, gh_pat: str | None) -> str:
    """Apply an approved change: open a profile PR, mark the row applied. Returns the PR URL.

    Raises if the change is missing, not pending, the PAT is absent, or the PR
    cannot be opened — the caller keeps the row pending so the user can retry.
    """
    with connection() as conn, conn.cursor() as cur:
        cur.execute(_SELECT_CHANGE, (change_id,))
        row = cur.fetchone()
    if row is None:
        raise ApplyError(f"no proposed change {change_id}")
    if row["status"] != "pending":
        raise ApplyError(f"change {change_id} is {row['status']}, not pending")

    diff = row["diff"]
    ops = [PatchOp.model_validate(o) for o in (diff.get("ops") or [])]
    if not ops:
        raise ApplyError("proposed change has no ops")
    if not gh_pat:
        raise ApplyError("GH_PAT_FOR_PROFILE_PR not configured — cannot open PR")

    pr_url = _open_profile_pr(ops, diff.get("summary", ""), change_id, gh_pat)

    def work(conn: Any) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE proposed_profile_changes SET status='applied', applied_at=now() "
                "WHERE id=%s",
                (change_id,),
            )

    execute_write(work)
    logger.info("self_update.applied", change_id=str(change_id), pr_url=pr_url)
    return pr_url


def _open_profile_pr(ops: list[PatchOp], change_summary: str, change_id: UUID, gh_pat: str) -> str:
    """Patch data/profile.yaml on a new branch and open a PR, all via the GitHub REST API."""
    repo = get_settings().github_repository
    today = date.today().isoformat()
    branch = f"profile-self-update-{today}-{str(change_id)[:8]}"
    headers = {
        "Authorization": f"Bearer {gh_pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(base_url=_GITHUB_API, headers=headers, timeout=30.0) as client:
        ref = client.get(f"/repos/{repo}/git/ref/heads/main")
        ref.raise_for_status()
        base_sha = ref.json()["object"]["sha"]

        file_resp = client.get(
            f"/repos/{repo}/contents/{_PROFILE_REPO_PATH}", params={"ref": "main"}
        )
        file_resp.raise_for_status()
        file_json = file_resp.json()
        current_text = base64.b64decode(file_json["content"]).decode("utf-8")

        # Patch the content fetched from main (not the bundled copy, which may be stale).
        new_text = apply_to_yaml_text(current_text, ops)

        create_ref = client.post(
            f"/repos/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        create_ref.raise_for_status()

        commit = client.put(
            f"/repos/{repo}/contents/{_PROFILE_REPO_PATH}",
            json={
                "message": f"chore: apply profile self-update {today}",
                "content": base64.b64encode(new_text.encode("utf-8")).decode("ascii"),
                "sha": file_json["sha"],
                "branch": branch,
            },
        )
        commit.raise_for_status()

        pr = client.post(
            f"/repos/{repo}/pulls",
            json={
                "title": f"chore: apply profile self-update {today}",
                "head": branch,
                "base": "main",
                "body": _pr_body(ops, change_summary),
            },
        )
        pr.raise_for_status()
        return pr.json()["html_url"]


def _pr_body(ops: list[PatchOp], change_summary: str) -> str:
    lines = ["Weekly preference self-update — approved in the webapp.", ""]
    if change_summary:
        lines += [f"**Summary:** {change_summary}", ""]
    lines.append("**Ops:**")
    for op in ops:
        lines.append(f"- `{op.op}` `{op.path}` — {op.reason}")
    lines += ["", "🤖 Generated by the policy-crawler weekly self-update."]
    return "\n".join(lines)


# ── Helpers ─────────────────────────────────────────────────────────────────


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, default=str)


def _log_llm_call(
    run_id: UUID | None, input_tokens: int, output_tokens: int, error: str | None
) -> None:
    from policy_crawler.self_update.propose_diff import _INPUT_PRICE_PER_1M, _OUTPUT_PRICE_PER_1M

    cost = (
        input_tokens / 1_000_000 * _INPUT_PRICE_PER_1M
        + output_tokens / 1_000_000 * _OUTPUT_PRICE_PER_1M
    )

    def work(conn: Any) -> None:
        with conn.cursor() as cur:
            cur.execute(
                _INSERT_LLM_CALL, (run_id, _MODEL, input_tokens, output_tokens, cost, error)
            )

    try:
        execute_write(work)
    except Exception as exc:  # noqa: BLE001 - cost logging must never break the run
        logger.warning("self_update.llm_call_log_failed", error=str(exc))


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    summary = run_self_update()
    print(
        f"Self-update: feedback={summary.feedback_total}, "
        f"ops_proposed={summary.ops_proposed}, "
        f"change_id={summary.change_id}, "
        f"cost=${summary.cost_usd:.4f}, "
        f"errors={summary.errors}"
    )
    from policy_crawler.db import get_pool

    with contextlib.suppress(Exception):
        get_pool().close()
    sys.exit(0)


if __name__ == "__main__":
    main()
