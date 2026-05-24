"""Shared pydantic models.

Populated by subsequent steps (database rows, fetcher RawJob, ranker
structured outputs). Step 01 only establishes the module so other modules
can import from it without an ImportError.
"""

from __future__ import annotations
