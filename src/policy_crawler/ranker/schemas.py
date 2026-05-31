"""Anthropic tool-use schemas for Pass 1 (Haiku screen) and Pass 2 (Sonnet deep score)."""

from __future__ import annotations

from anthropic.types import ToolParam

PASS1_TOOL: ToolParam = {
    "name": "score_pass1",
    "description": "Cheap screen of a single job posting against the user's preference profile.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fit_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "0=terrible fit, 100=perfect. Score ≤ 30 if any dealbreaker hits.",
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Your confidence in this score given the available information.",
            },
            "posting_type": {
                "type": "string",
                "enum": [
                    "role",
                    "fellowship",
                    "predoc",
                    "program_call",
                    "internal_rotation",
                    "unknown",
                ],
                "description": (
                    "Type of posting. Respect the provided type if it was already set"
                    " (not 'unknown')."
                ),
            },
            "geography_match": {
                "type": "string",
                "enum": ["primary", "secondary", "acceptable", "mismatch", "unknown"],
                "description": "How well the job location matches the user's geography preferences.",
            },
            "dealbreaker_hits": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List any dealbreakers that apply. Empty if none.",
            },
            "screen_reason": {
                "type": "string",
                "description": "1–2 sentence explanation of the score. Be concrete and specific.",
            },
        },
        "required": [
            "fit_score",
            "confidence",
            "posting_type",
            "geography_match",
            "dealbreaker_hits",
            "screen_reason",
        ],
    },
}

PASS2_TOOL: ToolParam = {
    "name": "score_pass2",
    "description": "Deep score and explanation for a single job posting that passed the Pass 1 screen.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fit_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Refined fit score after reading the full description.",
            },
            "reason_to_consider": {
                "type": "string",
                "description": "2–3 sentences: why this role is worth applying to.",
            },
            "concerns": {
                "type": "string",
                "description": "2–3 sentences: main reservations or risks.",
            },
            "matched_signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific phrases or signals from the description that match the profile.",
            },
            "missing_info": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Important things not clear from the posting (e.g., sponsorship, team size).",
            },
            "recommended_action": {
                "type": "string",
                "enum": ["apply_now", "monitor", "skip", "needs_human_review"],
                "description": "Suggested next action.",
            },
        },
        "required": [
            "fit_score",
            "reason_to_consider",
            "concerns",
            "matched_signals",
            "missing_info",
            "recommended_action",
        ],
    },
}
