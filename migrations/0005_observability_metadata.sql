-- Observability & guardrails (step 11).
--
-- runs.metadata:       free-form jsonb for run-level observability state. Step 11
--                      uses metadata->>'alert_sent_at' to dedupe failure/warning
--                      emails so a flapping run can't email more than once a day.
-- llm_calls.metadata:  per-call jsonb. Step 11 marks {"degraded": true} on Pass-2
--                      rows that ran on Haiku because the daily soft cap was hit.
--
-- ADD COLUMN IF NOT EXISTS is idempotent and transaction-safe.

ALTER TABLE runs      ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}';
ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}';
