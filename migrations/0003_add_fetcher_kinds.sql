-- Add new fetcher_kind enum values for ATS platforms found among existing
-- sources during step-09 source configuration (step 08 follow-up).
--
-- rippling: clean public JSON board API (api.rippling.com/.../board/{org}/jobs).
--
-- iCIMS and SaaSHR were investigated but deferred: iCIMS sits behind an AWS WAF
-- JS challenge (needs Playwright), and SaaSHR has only one source so far — both
-- stay as generic_html / disabled for now, so no enum value is added yet.
--
-- ADD VALUE IF NOT EXISTS is transaction-safe on PG12+; the value is only used by
-- later migrations / seeds, never in this transaction.

ALTER TYPE fetcher_kind ADD VALUE IF NOT EXISTS 'rippling';
