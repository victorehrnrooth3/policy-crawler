-- Webapp job-management view states (inbox/recommended/saved/all/archived).
--
-- saved_at:    user bookmarked the job (also records a 'save' feedback vote).
-- archived_at: user filed the job away — hidden from inbox/recommended/all/saved,
--              shown only in the Archived tab.
-- deleted_at:  user removed the job from the webapp. View-only soft delete: the
--              row stays in the DB for agent optimization and records NO feedback
--              signal (deletion is decluttering, not a preference judgment).
--
-- All three are idempotent ADD COLUMN IF NOT EXISTS; the jobs updated_at trigger
-- already covers them. Partial indexes keep the per-tab filters cheap.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS saved_at    timestamptz;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS deleted_at  timestamptz;

CREATE INDEX IF NOT EXISTS jobs_saved_idx    ON jobs (saved_at)    WHERE saved_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS jobs_archived_idx ON jobs (archived_at) WHERE archived_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS jobs_active_idx   ON jobs (deleted_at)  WHERE deleted_at IS NULL;
