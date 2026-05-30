"""Seed loader: parse data/sources.yaml and upsert into the sources table.

CLI usage:
    python -m policy_crawler.seed --file data/sources.yaml --validate-only
    python -m policy_crawler.seed --file data/sources.yaml --apply
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from policy_crawler.config import get_settings
from policy_crawler.db import connection, get_pool

_VALID_CATEGORIES = {
    "think_tank",
    "asset_manager_policy_institute",
    "geopolitical_risk",
    "corporate_policy_tech",
    "corporate_policy_defense",
    "corporate_policy_energy",
    "igo",
    "government",
    "predoc_program",
    "phd_program",
    "fellowship",
}
_VALID_FETCHER_KINDS = {
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "smartrecruiters",
    "workday_json",
    "rss",
    "sitemap",
    "generic_html",
    "playwright",
    "manual",
}

_UPSERT_SQL = """
INSERT INTO sources
    (name, careers_url, homepage_url, category, fetcher_kind,
     fetcher_config, geography_tags, priority, enabled, notes)
VALUES
    (%s, %s, %s, %s::source_category, %s::fetcher_kind,
     %s::jsonb, %s, %s, %s, %s)
ON CONFLICT (name, careers_url) DO UPDATE SET
    category       = EXCLUDED.category,
    fetcher_kind   = EXCLUDED.fetcher_kind,
    fetcher_config = EXCLUDED.fetcher_config,
    geography_tags = EXCLUDED.geography_tags,
    priority       = EXCLUDED.priority,
    notes          = EXCLUDED.notes,
    homepage_url   = EXCLUDED.homepage_url
RETURNING (xmax = 0) AS is_insert
"""


class SourceSeed(BaseModel):
    name: str
    homepage_url: str
    careers_url: str
    category: str
    fetcher_kind: str
    fetcher_config: dict = Field(default_factory=dict)
    geography_tags: list[str] = Field(default_factory=list)
    priority: int = Field(ge=1, le=5)
    enabled: bool = True
    notes: str = ""

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        if v not in _VALID_CATEGORIES:
            raise ValueError(f"Unknown category: {v!r}. Allowed: {sorted(_VALID_CATEGORIES)}")
        return v

    @field_validator("fetcher_kind")
    @classmethod
    def _check_fetcher_kind(cls, v: str) -> str:
        if v not in _VALID_FETCHER_KINDS:
            raise ValueError(
                f"Unknown fetcher_kind: {v!r}. Allowed: {sorted(_VALID_FETCHER_KINDS)}"
            )
        return v


class _SeedFile(BaseModel):
    version: int
    sources: list[SourceSeed]


def load_yaml(path: Path) -> list[SourceSeed]:
    """Parse and validate a sources YAML file. Raises on any validation error."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _SeedFile.model_validate(data).sources


def upsert_sources(seeds: list[SourceSeed]) -> tuple[int, int]:
    """Upsert *seeds* into the sources table.

    Returns ``(inserted, updated)`` counts.
    On conflict (name, careers_url): updates all fields except enabled and approved_by_me.
    """
    inserted = updated = 0
    with connection() as conn, conn.cursor() as cur:
        for s in seeds:
            cur.execute(
                _UPSERT_SQL,
                (
                    s.name,
                    s.careers_url,
                    s.homepage_url or None,
                    s.category,
                    s.fetcher_kind,
                    json.dumps(s.fetcher_config),
                    s.geography_tags,
                    s.priority,
                    s.enabled,
                    s.notes or None,
                ),
            )
            row = cur.fetchone()
            if row and row["is_insert"]:
                inserted += 1
            else:
                updated += 1
    return inserted, updated


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Seed policy-crawler sources table from YAML.")
    parser.add_argument("--file", required=True, help="Path to sources YAML file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="Apply upsert to Neon DB")
    group.add_argument(
        "--validate-only", action="store_true", help="Parse/validate YAML only (no DB)"
    )
    args = parser.parse_args()

    seeds = load_yaml(Path(args.file))
    print(f"Loaded {len(seeds)} source(s) from {args.file}.")

    if args.validate_only:
        print("Validation OK.")
        return

    if not get_settings().neon_database_url:
        print("Error: NEON_DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    inserted, updated = upsert_sources(seeds)
    print(f"Done: {inserted} inserted, {updated} updated.")
    get_pool.cache_clear()


if __name__ == "__main__":
    main()
