-- 013: Create source_fetch_flags table
-- Tracks domains with paywall / subscriber-wall status so the
-- FETCH FULL TEXT button can be disabled for those sources.

CREATE TABLE IF NOT EXISTS source_fetch_flags (
    domain              TEXT PRIMARY KEY,
    has_subscriber_wall BOOLEAN NOT NULL DEFAULT FALSE,
    has_paywall         BOOLEAN NOT NULL DEFAULT FALSE,
    source_name         TEXT,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_fetch_flags_type
    ON source_fetch_flags (has_subscriber_wall, has_paywall);
