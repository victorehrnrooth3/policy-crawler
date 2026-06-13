"""Tests for the patch-application engine — pure, no I/O."""

from __future__ import annotations

import pytest

from policy_crawler.ranker.profile import Profile
from policy_crawler.self_update.apply_diff import (
    ApplyError,
    PatchOp,
    apply,
    apply_to_yaml_text,
)

# A minimal-but-valid profile with a comment we expect ruamel to preserve.
_YAML = """\
version: 1
identity:
  summary: "test person"
  cv_url: "https://example.com"
career_thesis: "thesis"
topics:
  heavy:
    - name: "energy"  # keep this comment
      keywords: [a, b]
  medium: []
  low: []
  negative: []
geography:
  primary: [london]
  secondary: []
  acceptable: []
  hard_no: []
  timeline_note: "now"
seniority_fit: "early"
must_haves:
  - "topic match"
  - "quant character"
dealbreakers:
  - "pure finance"
soft_negatives: []
"""


def _op(op: str, path: str, value=None, reason: str = "test") -> PatchOp:
    return PatchOp(op=op, path=path, value=value, reason=reason)


def test_update_scalar() -> None:
    out = apply_to_yaml_text(_YAML, [_op("update", "geography.timeline_note", "later")])
    assert "later" in out
    assert Profile.model_validate_json  # sanity: model importable


def test_append_to_list() -> None:
    out = apply_to_yaml_text(_YAML, [_op("add", "soft_negatives[+]", "too junior")])
    profile = _load(out)
    assert "too junior" in profile.soft_negatives


def test_append_keyword_to_nested_topic() -> None:
    out = apply_to_yaml_text(_YAML, [_op("add", "topics.heavy[0].keywords[+]", "grid")])
    profile = _load(out)
    assert "grid" in profile.topics.heavy[0].keywords


def test_remove_list_element() -> None:
    out = apply_to_yaml_text(_YAML, [_op("remove", "must_haves[1]")])
    profile = _load(out)
    assert profile.must_haves == ["topic match"]


def test_comment_preserved() -> None:
    out = apply_to_yaml_text(_YAML, [_op("update", "geography.timeline_note", "later")])
    assert "# keep this comment" in out


def test_forbidden_version_path() -> None:
    with pytest.raises(ApplyError):
        apply_to_yaml_text(_YAML, [_op("update", "version", 2)])


def test_forbidden_cv_url_path() -> None:
    with pytest.raises(ApplyError):
        apply_to_yaml_text(_YAML, [_op("update", "identity.cv_url", "https://evil.test")])


def test_cannot_empty_dealbreakers() -> None:
    with pytest.raises(ApplyError):
        apply_to_yaml_text(_YAML, [_op("remove", "dealbreakers[0]")])


def test_cannot_empty_must_haves() -> None:
    ops = [_op("remove", "must_haves[1]"), _op("remove", "must_haves[0]")]
    with pytest.raises(ApplyError):
        apply_to_yaml_text(_YAML, ops)


def test_update_missing_key_raises() -> None:
    with pytest.raises(ApplyError):
        apply_to_yaml_text(_YAML, [_op("update", "geography.nonexistent", "x")])


def test_index_out_of_range_raises() -> None:
    with pytest.raises(ApplyError):
        apply_to_yaml_text(_YAML, [_op("update", "must_haves[9]", "x")])


def test_apply_returns_validated_profile() -> None:
    profile = _load(_YAML)
    updated = apply(profile, [_op("add", "soft_negatives[+]", "slow bureaucracy")])
    assert isinstance(updated, Profile)
    assert "slow bureaucracy" in updated.soft_negatives
    # original is untouched (pure function)
    assert profile.soft_negatives == []


def _load(yaml_text: str) -> Profile:
    import yaml as _y

    return Profile.model_validate(_y.safe_load(yaml_text))
