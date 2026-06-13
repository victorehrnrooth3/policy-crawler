-- 2-tier weekly pipeline (step-09 / architecture simplification).
--
-- camoufox:      Tier-2 fetcher — a Camoufox (Firefox) browser render + Haiku
--                extraction. Replaces the dead generic_html/playwright/sitemap/rss
--                strategies and unlocks JS/WAF-gated career pages (e.g. iCIMS).
-- crawl_extract: llm_call_kind for the per-page Haiku extraction done by the
--                camoufox fetcher (distinct from pass1/pass2/discovery cost).
-- weekly:        run_kind for the unified weekly pipeline (crawl + rank + digest
--                + discovery + self-update) that replaces the separate daily run.
--
-- ADD VALUE IF NOT EXISTS is transaction-safe on PG12+; the new values are only
-- referenced by later seeds / app code, never in this transaction.

ALTER TYPE fetcher_kind  ADD VALUE IF NOT EXISTS 'camoufox';
ALTER TYPE llm_call_kind ADD VALUE IF NOT EXISTS 'crawl_extract';
ALTER TYPE run_kind      ADD VALUE IF NOT EXISTS 'weekly';
