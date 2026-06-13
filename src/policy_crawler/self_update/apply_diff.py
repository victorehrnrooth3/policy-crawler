"""Apply a structured patch list to the preference profile.

The diff is a list of ``PatchOp`` (op / path / value / reason). Paths use a small
JSON-Pointer-like syntax over the profile's nested structure:

- ``must_haves[2]``            — the 3rd must-have (0-indexed)
- ``must_haves[+]``            — append to must-haves
- ``topics.heavy[2].keywords`` — the keywords list of the 3rd heavy topic
- ``geography.timeline_note``  — a scalar field

Ops: ``update`` (set an existing key/index), ``add`` (set a key, insert at an
index, or append with ``[+]``), ``remove`` (delete a key/index).

Two entry points share one in-place engine:
- ``apply(profile, ops)`` mutates a dict copy and re-validates against the Pydantic
  ``Profile`` — used to verify a diff is structurally sound before persisting.
- ``apply_to_yaml(yaml_path, ops)`` patches the real file via ``ruamel.yaml`` so
  comments and key ordering in untouched sections are preserved.

Guardrails are enforced in the engine (so both paths get them): no op may touch
``version`` or ``identity.cv_url``, and no op may leave ``must_haves`` or
``dealbreakers`` empty.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from ruamel.yaml import YAML

from policy_crawler.ranker.profile import Profile

# Paths that must never be modified by an automated diff.
_FORBIDDEN_PATHS = ("version", "identity.cv_url")
# Lists that must never be emptied by a diff (a dealbreaker/must-have removal
# requires explicit human action, not weekly drift).
_PROTECTED_NONEMPTY = ("must_haves", "dealbreakers")

_SEGMENT_RE = re.compile(r"^([^\[\]]+)((?:\[[^\[\]]+\])*)$")
_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")


class PatchOp(BaseModel):
    op: Literal["add", "remove", "update"]
    path: str
    value: Any = None
    reason: str


class ApplyError(ValueError):
    """Raised when a patch op cannot be applied or violates a guardrail."""


@dataclass(frozen=True)
class _Key:
    name: str


@dataclass(frozen=True)
class _Index:
    i: int


@dataclass(frozen=True)
class _Append:
    pass


_Accessor = _Key | _Index | _Append


def _parse_path(path: str) -> list[_Accessor]:
    if not path or not path.strip():
        raise ApplyError("empty path")
    accessors: list[_Accessor] = []
    for segment in path.split("."):
        m = _SEGMENT_RE.match(segment)
        if not m:
            raise ApplyError(f"unparseable path segment: {segment!r}")
        key, brackets = m.group(1), m.group(2)
        accessors.append(_Key(key))
        for raw in _BRACKET_RE.findall(brackets):
            if raw == "+":
                accessors.append(_Append())
            else:
                try:
                    accessors.append(_Index(int(raw)))
                except ValueError as exc:
                    raise ApplyError(f"non-integer index in path: {segment!r}") from exc
    return accessors


def _descend(container: Any, accessor: _Accessor, path: str) -> Any:
    if isinstance(accessor, _Key):
        if not isinstance(container, dict) or accessor.name not in container:
            raise ApplyError(f"no key {accessor.name!r} while resolving {path!r}")
        return container[accessor.name]
    if isinstance(accessor, _Index):
        if not isinstance(container, list) or not (0 <= accessor.i < len(container)):
            raise ApplyError(f"index {accessor.i} out of range while resolving {path!r}")
        return container[accessor.i]
    raise ApplyError(f"append accessor not allowed mid-path in {path!r}")


def _apply_one(data: dict[str, Any], op: PatchOp) -> None:
    normalized = op.path.strip()
    if normalized in _FORBIDDEN_PATHS or any(
        normalized.startswith(f"{p}.") or normalized.startswith(f"{p}[") for p in _FORBIDDEN_PATHS
    ):
        raise ApplyError(f"op targets a protected path: {op.path!r}")

    accessors = _parse_path(normalized)
    *parents, last = accessors

    parent: Any = data
    for acc in parents:
        parent = _descend(parent, acc, normalized)

    if op.op == "add":
        if isinstance(last, _Append):
            if not isinstance(parent, list):
                raise ApplyError(f"[+] target is not a list: {op.path!r}")
            parent.append(op.value)
        elif isinstance(last, _Key):
            if not isinstance(parent, dict):
                raise ApplyError(f"add target parent is not a mapping: {op.path!r}")
            parent[last.name] = op.value
        else:  # _Index — insert at position
            if not isinstance(parent, list) or not (0 <= last.i <= len(parent)):
                raise ApplyError(f"add index out of range: {op.path!r}")
            parent.insert(last.i, op.value)
    elif op.op == "update":
        if isinstance(last, _Key):
            if not isinstance(parent, dict) or last.name not in parent:
                raise ApplyError(f"update target does not exist: {op.path!r}")
            parent[last.name] = op.value
        elif isinstance(last, _Index):
            if not isinstance(parent, list) or not (0 <= last.i < len(parent)):
                raise ApplyError(f"update index out of range: {op.path!r}")
            parent[last.i] = op.value
        else:
            raise ApplyError(f"cannot update with [+] append accessor: {op.path!r}")
    else:  # remove
        if isinstance(last, _Key):
            if not isinstance(parent, dict) or last.name not in parent:
                raise ApplyError(f"remove target does not exist: {op.path!r}")
            del parent[last.name]
        elif isinstance(last, _Index):
            if not isinstance(parent, list) or not (0 <= last.i < len(parent)):
                raise ApplyError(f"remove index out of range: {op.path!r}")
            del parent[last.i]
        else:
            raise ApplyError(f"cannot remove with [+] append accessor: {op.path!r}")


def _enforce_nonempty(data: dict[str, Any]) -> None:
    for key in _PROTECTED_NONEMPTY:
        value = data.get(key)
        if not isinstance(value, list) or len(value) == 0:
            raise ApplyError(f"diff would leave {key!r} empty — refused")


def apply_ops(data: dict[str, Any], ops: list[PatchOp]) -> None:
    """Apply *ops* to *data* in place (works on plain dicts and ruamel maps)."""
    for op in ops:
        _apply_one(data, op)
    _enforce_nonempty(data)


def apply(profile: Profile, ops: list[PatchOp]) -> Profile:
    """Return a new validated Profile with *ops* applied. Pure (no I/O)."""
    data = copy.deepcopy(profile.model_dump())
    apply_ops(data, ops)
    return Profile.model_validate(data)


def apply_to_yaml_text(yaml_text: str, ops: list[PatchOp]) -> str:
    """Apply *ops* to raw YAML *text*, preserving comments/order. Returns the new text.

    Validates the result against the Pydantic schema before returning, so a diff
    that produces a structurally invalid profile raises rather than emitting garbage.
    Takes text (not a path) so the webapp can patch content fetched from GitHub on
    Vercel's read-only filesystem.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    data = yaml.load(yaml_text)

    apply_ops(data, ops)
    Profile.model_validate(data)  # guard: never emit an invalid profile

    buf = StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def apply_to_yaml(yaml_path: Path, ops: list[PatchOp]) -> str:
    """Apply *ops* to the YAML file at *yaml_path*. Returns the new text."""
    return apply_to_yaml_text(yaml_path.read_text(encoding="utf-8"), ops)
