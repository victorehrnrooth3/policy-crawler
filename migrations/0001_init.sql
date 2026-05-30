-- Initial schema for policy-crawler.
-- Applied in a single transaction by migrations/_apply.py.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Enum types ────────────────────────────────────────────────────────────────

CREATE TYPE source_category AS ENUM (
    'think_tank',
    'asset_manager_policy_institute',
    'geopolitical_risk',
    'corporate_policy_tech',
    'corporate_policy_defense',
    'corporate_policy_energy',
    'igo',
    'government',
    'predoc_program',
    'phd_program',
    'fellowship'
);

CREATE TYPE fetcher_kind AS ENUM (
    'greenhouse',
    'lever',
    'ashby',
    'workable',
    'smartrecruiters',
    'workday_json',
    'rss',
    'sitemap',
    'generic_html',
    'playwright',
    'manual'
);

CREATE TYPE posting_type AS ENUM (
    'role',
    'fellowship',
    'predoc',
    'program_call',
    'internal_rotation',
    'unknown'
);

CREATE TYPE remote_policy AS ENUM (
    'onsite',
    'hybrid',
    'remote',
    'unknown'
);

CREATE TYPE seniority AS ENUM (
    'intern',
    'early_career',
    'mid',
    'senior',
    'lead',
    'exec',
    'unknown'
);

CREATE TYPE vote_kind AS ENUM (
    'up',
    'down',
    'save',
    'applied',
    'hidden'
);

CREATE TYPE vote_source AS ENUM (
    'email_link',
    'webapp',
    'auto'
);

CREATE TYPE suggestion_status AS ENUM (
    'pending',
    'approved',
    'rejected',
    'snoozed'
);

CREATE TYPE change_status AS ENUM (
    'pending',
    'applied',
    'rejected'
);

CREATE TYPE run_kind AS ENUM (
    'daily',
    'weekly_discovery',
    'weekly_self_update',
    'manual'
);

CREATE TYPE run_status AS ENUM (
    'started',
    'succeeded',
    'failed',
    'partial'
);

CREATE TYPE llm_call_kind AS ENUM (
    'pass1',
    'pass2',
    'discovery',
    'self_update',
    'manual_extract'
);

-- ── Trigger function ──────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$;

-- ── Tables ────────────────────────────────────────────────────────────────────

CREATE TABLE sources (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text        NOT NULL,
    careers_url     text        NOT NULL,
    homepage_url    text,
    category        source_category NOT NULL,
    fetcher_kind    fetcher_kind    NOT NULL,
    fetcher_config  jsonb       NOT NULL DEFAULT '{}',
    geography_tags  text[]      NOT NULL DEFAULT '{}',
    priority        int         NOT NULL DEFAULT 3,
    enabled         bool        NOT NULL DEFAULT true,
    approved_by_me  bool        NOT NULL DEFAULT true,
    last_checked_at timestamptz,
    last_success_at timestamptz,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id               uuid        NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    canonical_id            text        NOT NULL,
    url                     text        NOT NULL,
    title                   text        NOT NULL,
    company                 text,
    location_raw            text,
    location_parsed         jsonb,
    remote_policy           remote_policy   NOT NULL DEFAULT 'unknown',
    seniority               seniority       NOT NULL DEFAULT 'unknown',
    posting_type            posting_type    NOT NULL DEFAULT 'unknown',
    description_raw         text,
    description_clean       text,
    compensation            jsonb,
    first_seen_at           timestamptz NOT NULL DEFAULT now(),
    last_seen_at            timestamptz NOT NULL DEFAULT now(),
    closed_at               timestamptz,
    -- pass1_confidence is text, not an enum: values are low/med/high
    pass1_score             int,
    pass1_reason            text,
    pass1_confidence        text,
    pass1_dealbreaker_hits  text[],
    pass2_score             int,
    pass2_reason_to_consider text,
    pass2_concerns          text,
    pass2_matched_signals   text[],
    pass2_missing_info      text[],
    pass2_recommended_action text,
    digest_sent_at          timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, canonical_id)
);

CREATE TABLE job_versions (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           uuid        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    title            text,
    location_raw     text,
    description_clean text,
    change_summary   text,
    observed_at      timestamptz NOT NULL DEFAULT now(),
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feedback (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id     uuid        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    vote       vote_kind   NOT NULL,
    source     vote_source NOT NULL,
    freetext   text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE suggested_sources (
    id                   uuid               PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 text               NOT NULL,
    careers_url          text               NOT NULL,
    category             source_category,
    fetcher_kind         fetcher_kind,
    rationale            text,
    example_similar_jobs text[],
    status               suggestion_status  NOT NULL DEFAULT 'pending',
    proposed_at          timestamptz        NOT NULL DEFAULT now(),
    decided_at           timestamptz,
    created_at           timestamptz        NOT NULL DEFAULT now(),
    updated_at           timestamptz        NOT NULL DEFAULT now()
);

CREATE TABLE proposed_profile_changes (
    id                  uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    diff                jsonb         NOT NULL,
    rationale_per_change jsonb        NOT NULL,
    status              change_status NOT NULL DEFAULT 'pending',
    proposed_at         timestamptz   NOT NULL DEFAULT now(),
    applied_at          timestamptz,
    created_at          timestamptz   NOT NULL DEFAULT now(),
    updated_at          timestamptz   NOT NULL DEFAULT now()
);

CREATE TABLE runs (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    kind            run_kind    NOT NULL,
    status          run_status  NOT NULL DEFAULT 'started',
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    jobs_seen       int         NOT NULL DEFAULT 0,
    jobs_new        int         NOT NULL DEFAULT 0,
    llm_calls_count int         NOT NULL DEFAULT 0,
    total_cost_usd  numeric(10,4) NOT NULL DEFAULT 0,
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE llm_calls (
    id            uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        uuid          REFERENCES runs(id) ON DELETE SET NULL,
    kind          llm_call_kind NOT NULL,
    model         text          NOT NULL,
    input_tokens  int,
    output_tokens int,
    cost_usd      numeric(10,6) NOT NULL DEFAULT 0,
    latency_ms    int,
    error         text,
    created_at    timestamptz   NOT NULL DEFAULT now()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX ON sources (enabled, category);
CREATE INDEX ON sources (fetcher_kind);

-- jobs: UNIQUE (source_id, canonical_id) already creates the covering index
CREATE INDEX ON jobs (last_seen_at DESC);
CREATE INDEX ON jobs (pass1_score DESC NULLS LAST);
CREATE INDEX ON jobs (pass2_score DESC NULLS LAST);
CREATE INDEX ON jobs (digest_sent_at) WHERE digest_sent_at IS NULL;

CREATE INDEX ON feedback (job_id, created_at DESC);

CREATE INDEX ON suggested_sources (status);
CREATE INDEX ON proposed_profile_changes (status);

CREATE INDEX ON runs (kind, started_at DESC);
CREATE INDEX ON llm_calls (run_id);

-- ── Triggers ──────────────────────────────────────────────────────────────────

CREATE TRIGGER trg_sources_updated_at
    BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_suggested_sources_updated_at
    BEFORE UPDATE ON suggested_sources
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_proposed_profile_changes_updated_at
    BEFORE UPDATE ON proposed_profile_changes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
