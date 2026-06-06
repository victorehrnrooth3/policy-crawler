-- Adds single-use token tracking and profile version history (step 07).
-- Applied in a single transaction by migrations/_apply.py.

CREATE TABLE consumed_tokens (
    nonce       TEXT        PRIMARY KEY,
    consumed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE profile_versions (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    version     INT         NOT NULL,
    profile     JSONB       NOT NULL,
    source      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON profile_versions (version DESC);
