"""Tests for ranker/schemas.py — verify Anthropic tool-use dict structure."""

from __future__ import annotations

from policy_crawler.ranker.schemas import PASS1_TOOL, PASS2_TOOL


def _required_fields(tool: dict) -> set[str]:
    return set(tool["input_schema"].get("required", []))


def _properties(tool: dict) -> set[str]:
    return set(tool["input_schema"]["properties"].keys())


# ── PASS1_TOOL ────────────────────────────────────────────────────────────────


def test_pass1_tool_name() -> None:
    assert PASS1_TOOL["name"] == "score_pass1"


def test_pass1_tool_has_description() -> None:
    assert PASS1_TOOL.get("description")


def test_pass1_schema_type_object() -> None:
    assert PASS1_TOOL["input_schema"]["type"] == "object"


def test_pass1_required_fields_present() -> None:
    required = _required_fields(PASS1_TOOL)
    assert required == {
        "fit_score",
        "confidence",
        "posting_type",
        "geography_match",
        "dealbreaker_hits",
        "screen_reason",
    }


def test_pass1_fit_score_integer_with_range() -> None:
    fs = PASS1_TOOL["input_schema"]["properties"]["fit_score"]
    assert fs["type"] == "integer"
    assert fs["minimum"] == 0
    assert fs["maximum"] == 100


def test_pass1_confidence_enum() -> None:
    conf = PASS1_TOOL["input_schema"]["properties"]["confidence"]
    assert conf["type"] == "string"
    assert set(conf["enum"]) == {"low", "medium", "high"}


def test_pass1_posting_type_enum() -> None:
    pt = PASS1_TOOL["input_schema"]["properties"]["posting_type"]
    expected = {"role", "fellowship", "predoc", "program_call", "internal_rotation", "unknown"}
    assert set(pt["enum"]) == expected


def test_pass1_geography_match_enum() -> None:
    gm = PASS1_TOOL["input_schema"]["properties"]["geography_match"]
    expected = {"primary", "secondary", "acceptable", "mismatch", "unknown"}
    assert set(gm["enum"]) == expected


def test_pass1_dealbreaker_hits_array_of_strings() -> None:
    db = PASS1_TOOL["input_schema"]["properties"]["dealbreaker_hits"]
    assert db["type"] == "array"
    assert db["items"]["type"] == "string"


# ── PASS2_TOOL ────────────────────────────────────────────────────────────────


def test_pass2_tool_name() -> None:
    assert PASS2_TOOL["name"] == "score_pass2"


def test_pass2_tool_has_description() -> None:
    assert PASS2_TOOL.get("description")


def test_pass2_schema_type_object() -> None:
    assert PASS2_TOOL["input_schema"]["type"] == "object"


def test_pass2_required_fields_present() -> None:
    required = _required_fields(PASS2_TOOL)
    assert required == {
        "fit_score",
        "reason_to_consider",
        "concerns",
        "matched_signals",
        "missing_info",
        "recommended_action",
    }


def test_pass2_fit_score_integer_with_range() -> None:
    fs = PASS2_TOOL["input_schema"]["properties"]["fit_score"]
    assert fs["type"] == "integer"
    assert fs["minimum"] == 0
    assert fs["maximum"] == 100


def test_pass2_recommended_action_enum() -> None:
    ra = PASS2_TOOL["input_schema"]["properties"]["recommended_action"]
    expected = {"apply_now", "monitor", "skip", "needs_human_review"}
    assert set(ra["enum"]) == expected


def test_pass2_matched_signals_array_of_strings() -> None:
    ms = PASS2_TOOL["input_schema"]["properties"]["matched_signals"]
    assert ms["type"] == "array"
    assert ms["items"]["type"] == "string"


def test_pass2_missing_info_array_of_strings() -> None:
    mi = PASS2_TOOL["input_schema"]["properties"]["missing_info"]
    assert mi["type"] == "array"
    assert mi["items"]["type"] == "string"
