"""Tests for ranker/profile.py — YAML loading, validation, and prompt rendering."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from policy_crawler.ranker.profile import (
    Profile,
    format_exemplars,
    load_profile,
    profile_for_prompt,
)

_MINIMAL_YAML = textwrap.dedent("""\
    version: 1
    identity:
      summary: "Test analyst with economics background."
    career_thesis: "Targeting energy and defense policy roles."
    topics:
      heavy:
        - name: "energy policy"
          keywords: [energy, electricity]
      medium:
        - name: "macro"
          keywords: [macroeconomics]
      low: []
      negative:
        - name: "pure finance"
          keywords: [trading, IB]
    geography:
      primary: [london]
      secondary: [nyc]
      acceptable: [remote]
      hard_no: []
      timeline_note: "London now."
    must_haves:
      - "Topic match"
    dealbreakers:
      - "No visa sponsorship for US roles"
    soft_negatives:
      - "Slow bureaucratic roles"
    exemplars:
      liked:
        - title: "Energy Analyst"
          company: "CGEP"
          why: "Deep energy policy shop."
          topic: "energy policy"
      disliked:
        - title: "IB Analyst"
          company: "Goldman"
          why: "Pure finance."
          topic: "pure finance"
""")


@pytest.fixture
def minimal_yaml_path(tmp_path: Path) -> Path:
    p = tmp_path / "profile.yaml"
    p.write_text(_MINIMAL_YAML, encoding="utf-8")
    return p


def test_load_real_profile() -> None:
    """The actual data/profile.yaml must load and validate without error."""
    profile = load_profile()
    assert isinstance(profile, Profile)
    assert profile.version == 1
    assert profile.identity.summary
    assert profile.career_thesis
    assert len(profile.topics.heavy) >= 1
    assert len(profile.geography.primary) >= 1
    assert len(profile.dealbreakers) >= 1
    assert len(profile.exemplars.liked) >= 1


def test_load_minimal(minimal_yaml_path: Path) -> None:
    profile = load_profile(minimal_yaml_path)
    assert profile.identity.summary == "Test analyst with economics background."
    assert profile.topics.heavy[0].name == "energy policy"
    assert "energy" in profile.topics.heavy[0].keywords
    assert profile.geography.primary == ["london"]


def test_profile_for_prompt_contains_key_sections() -> None:
    profile = load_profile()
    text = profile_for_prompt(profile)
    assert "## About me" in text
    assert "## Career thesis" in text
    assert "## Topics" in text
    assert "## Geography" in text
    assert "## Dealbreakers" in text


def test_profile_for_prompt_within_token_budget() -> None:
    profile = load_profile()
    text = profile_for_prompt(profile)
    # Budget is 1500 tokens * 4 chars ≈ 6000 chars
    assert len(text) <= 6_100  # small margin for truncation suffix


def test_profile_for_prompt_heavy_topics_listed() -> None:
    profile = load_profile()
    text = profile_for_prompt(profile)
    for topic in profile.topics.heavy:
        assert topic.name in text


def test_format_exemplars_includes_liked_and_disliked(minimal_yaml_path: Path) -> None:
    profile = load_profile(minimal_yaml_path)
    text = format_exemplars(profile)
    assert "Liked" in text
    assert "Disliked" in text
    assert "CGEP" in text
    assert "Goldman" in text


def test_format_exemplars_respects_n_limit() -> None:
    profile = load_profile()
    text = format_exemplars(profile, liked_n=2, disliked_n=1)
    # Should contain at most 2 liked and 1 disliked
    liked_count = text.count("**Liked")
    disliked_count = text.count("**Disliked")
    assert liked_count == 1
    assert disliked_count == 1


def test_profile_missing_required_field_raises(tmp_path: Path) -> None:
    bad = yaml.dump({"version": 1})  # missing identity, career_thesis, etc.
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(ValidationError):
        load_profile(p)
