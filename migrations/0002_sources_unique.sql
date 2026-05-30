-- Add unique constraint on sources(name, careers_url) to support ON CONFLICT upserts
-- from the seed loader (migrations/_apply.py uses the direct URL).

ALTER TABLE sources
    ADD CONSTRAINT sources_name_careers_url_unique UNIQUE (name, careers_url);
