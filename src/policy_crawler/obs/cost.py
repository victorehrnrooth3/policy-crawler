"""Cost accounting and soft/hard spend caps (step 11).

This is the single source of truth for Anthropic prices. When prices change, edit
``PRICES_USD_PER_M_TOKENS`` here and nowhere else. The per-module ``_cost`` helpers
in the ranker / crawler delegate here so the constants never drift.

Spend functions sum ``llm_calls.cost_usd`` straight from the DB, so they capture
*every* call kind (pass1, pass2, discovery, self_update, crawl_extract) without
each pipeline having to thread its own cost back up.
"""

from __future__ import annotations

from datetime import date
from typing import LiteralString
from uuid import UUID

import structlog

from policy_crawler.config import get_settings
from policy_crawler.db import connection

logger = structlog.get_logger(__name__)

# USD per 1M tokens. Keyed by model-id *prefix* so dated ids (e.g.
# "claude-haiku-4-5-20251001") resolve to the same entry as the base id.
# Step 03 doc cites these prices; keep them in sync.
PRICES_USD_PER_M_TOKENS: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
}


def _prices_for(model: str) -> dict[str, float] | None:
    for prefix, prices in PRICES_USD_PER_M_TOKENS.items():
        if model.startswith(prefix):
            return prices
    return None


def compute_call_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    """USD cost of one call. Returns 0.0 for an unknown model (logged once)."""
    prices = _prices_for(model)
    if prices is None:
        logger.warning("cost.unknown_model", model=model)
        return 0.0
    return in_tokens / 1_000_000 * prices["input"] + out_tokens / 1_000_000 * prices["output"]


_SUM_BY_DAY: LiteralString = (
    "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM llm_calls WHERE created_at::date = %s"
)
_SUM_BY_MONTH: LiteralString = (
    "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM llm_calls "
    "WHERE date_trunc('month', created_at) = date_trunc('month', %s::date)"
)
_SUM_BY_RUN: LiteralString = (
    "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM llm_calls WHERE run_id = %s"
)


def _sum_cost(query: LiteralString, params: tuple[object, ...]) -> float:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    return float(row["total"]) if row else 0.0


def daily_spend(day: date) -> float:
    """Total LLM spend for the calendar day *day* (UTC)."""
    return _sum_cost(_SUM_BY_DAY, (day,))


def monthly_spend(month: date) -> float:
    """Total LLM spend for the calendar month containing *month* (UTC)."""
    return _sum_cost(_SUM_BY_MONTH, (month,))


def run_spend(run_id: UUID) -> float:
    """Total LLM spend attributed to a single run."""
    return _sum_cost(_SUM_BY_RUN, (run_id,))


def run_call_count(run_id: UUID) -> int:
    """Number of llm_calls rows attributed to a single run."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM llm_calls WHERE run_id = %s", (run_id,))
        row = cur.fetchone()
    return int(row["n"]) if row else 0


def should_degrade_to_haiku(today: date) -> bool:
    """True if today's spend has already reached the daily soft cap.

    Checked *before* Pass 2 starts; when true, Pass 2 runs on Haiku instead of
    Sonnet. A soft cap — it degrades quality, it does not abort the run.
    """
    cap = get_settings().daily_soft_cap_usd
    spent = daily_spend(today)
    if spent >= cap:
        logger.warning("cost.daily_soft_cap_reached", spent=round(spent, 4), cap=cap)
        return True
    return False
