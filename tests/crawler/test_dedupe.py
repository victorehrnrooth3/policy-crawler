from __future__ import annotations

import uuid

from policy_crawler.crawler.dedupe import dedupe


def _job(title: str, company: str, city: str = "dc") -> dict:
    return {
        "source_id": uuid.uuid4(),
        "canonical_id": f"{company}-{title}",
        "title": title,
        "company": company,
        "location_parsed": {"city": city, "is_remote": False},
        "url": "https://example.com",
    }


def test_dedup_same_job_different_sources() -> None:
    job1 = _job("Policy Analyst", "Brookings Institution")
    job2 = dict(job1)
    job2["source_id"] = uuid.uuid4()
    job2["canonical_id"] = "different-id"

    result = dedupe([job1, job2])
    assert len(result) == 1


def test_dedup_different_titles_both_kept() -> None:
    job1 = _job("Policy Analyst", "RAND")
    job2 = _job("Research Fellow", "RAND")

    result = dedupe([job1, job2])
    assert len(result) == 2


def test_dedup_seniority_prefix_collapsed() -> None:
    job1 = _job("Senior Policy Analyst", "CSIS")
    job2 = _job("Policy Analyst", "CSIS")  # same after stripping seniority

    result = dedupe([job1, job2])
    assert len(result) == 1


def test_dedup_different_cities_both_kept() -> None:
    job1 = _job("Policy Analyst", "Eurasia Group", "nyc")
    job2 = _job("Policy Analyst", "Eurasia Group", "london")

    result = dedupe([job1, job2])
    assert len(result) == 2


def test_dedup_empty_list() -> None:
    assert dedupe([]) == []


def test_dedup_preserves_first_occurrence() -> None:
    job1 = _job("Economist", "IMF", "dc")
    job2 = dict(job1)
    job2["canonical_id"] = "different"
    job2["url"] = "https://other.com"

    result = dedupe([job1, job2])
    assert result[0]["canonical_id"] == job1["canonical_id"]
